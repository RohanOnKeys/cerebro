"""GitHub App authentication: PEM → JWT → installation access token."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from cerebro.config import settings

GITHUB_API_BASE = "https://api.github.com"
JWT_LIFETIME = timedelta(minutes=9)
TOKEN_REFRESH_SKEW = timedelta(minutes=5)


class GitHubAuthError(RuntimeError):
    """Raised when GitHub App credentials or token exchange fail."""


def decode_private_key_pem(private_key_b64: str) -> str:
    """Decode a base64-encoded PEM private key to PEM text."""
    raw = (private_key_b64 or "").strip()
    if not raw:
        raise GitHubAuthError("GITHUB_PRIVATE_KEY_B64 is empty")
    try:
        pem = base64.b64decode(raw, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitHubAuthError("GITHUB_PRIVATE_KEY_B64 is not valid base64 PEM") from exc
    if "BEGIN" not in pem:
        raise GitHubAuthError("decoded key is not a PEM document")
    return pem


@dataclass
class _CachedToken:
    token: str
    expires_at: datetime


class GitHubAppAuth:
    """Mint and cache GitHub App installation tokens.

    Flow: load PEM → sign short-lived JWT (iss=app_id) → exchange for an
    installation access token → cache until refresh skew (T-5m).
    """

    def __init__(
        self,
        *,
        app_id: str | None = None,
        private_key_b64: str | None = None,
        installation_id: str | None = None,
        http_client: httpx.Client | None = None,
        api_base: str = GITHUB_API_BASE,
    ) -> None:
        if app_id is None or private_key_b64 is None or installation_id is None:
            if app_id is None:
                app_id = settings.github_app_id
            if private_key_b64 is None:
                private_key_b64 = settings.github_private_key_b64
            if installation_id is None:
                installation_id = settings.github_installation_id

        self.app_id = (app_id or "").strip()
        self.installation_id = (installation_id or "").strip()
        self._pem = decode_private_key_pem(private_key_b64 or "")
        self.api_base = api_base.rstrip("/")
        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None
        self._cached: _CachedToken | None = None

        if not self.app_id:
            raise GitHubAuthError("GITHUB_APP_ID is empty")
        if not self.installation_id:
            raise GitHubAuthError("GITHUB_INSTALLATION_ID is empty")

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> GitHubAppAuth:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def make_jwt(self, *, now: datetime | None = None) -> str:
        """Sign an RS256 JWT asserting this GitHub App identity."""
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        iat = int(moment.timestamp()) - 60  # clock skew allowance
        exp = int((moment + JWT_LIFETIME).timestamp())
        payload: dict[str, Any] = {"iat": iat, "exp": exp, "iss": self.app_id}
        return jwt.encode(payload, self._pem, algorithm="RS256")

    def _token_is_fresh(self, *, now: datetime) -> bool:
        if self._cached is None:
            return False
        return now < (self._cached.expires_at - TOKEN_REFRESH_SKEW)

    def get_installation_token(
        self, *, now: datetime | None = None, force_refresh: bool = False
    ) -> str:
        """Return a cached installation token, refreshing at T-5m before expiry."""
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)

        if not force_refresh and self._token_is_fresh(now=moment):
            assert self._cached is not None
            return self._cached.token

        app_jwt = self.make_jwt(now=moment)
        response = self._http.post(
            f"{self.api_base}/app/installations/{self.installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubAuthError(
                f"installation token exchange failed: {exc.response.status_code}"
            ) from exc

        body = response.json()
        token = body.get("token")
        expires_raw = body.get("expires_at")
        if not token or not expires_raw:
            raise GitHubAuthError("installation token response missing token/expires_at")

        expires_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        self._cached = _CachedToken(token=token, expires_at=expires_at)
        return token

    def clear_cache(self) -> None:
        """Drop the cached installation token."""
        self._cached = None
