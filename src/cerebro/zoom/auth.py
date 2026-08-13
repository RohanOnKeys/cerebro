"""Zoom auth: Server-to-Server OAuth (account-level, no user interaction).

account_credentials is the grant type Zoom recommends for exactly this
shape, one shared account, no per-user consent flow. Simpler than
Google's JWT-bearer exchange: no JWT signing at all, just Basic auth on
the token endpoint.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from cerebro.config import settings

TOKEN_URL = "https://zoom.us/oauth/token"
TOKEN_REFRESH_SKEW = timedelta(minutes=5)


class ZoomAuthError(RuntimeError):
    """Raised when Zoom credentials or token exchange fail."""


@dataclass
class _CachedToken:
    token: str
    expires_at: datetime


class ZoomAuth:
    """Mint and cache Zoom Server-to-Server OAuth access tokens."""

    def __init__(
        self,
        *,
        account_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        http_client: httpx.Client | None = None,
        token_url: str = TOKEN_URL,
    ) -> None:
        self.account_id = (
            account_id if account_id is not None else settings.zoom_account_id
        ).strip()
        self.client_id = (client_id if client_id is not None else settings.zoom_client_id).strip()
        self.client_secret = (
            client_secret if client_secret is not None else settings.zoom_client_secret
        ).strip()
        self.token_url = token_url

        if not self.account_id:
            raise ZoomAuthError("ZOOM_ACCOUNT_ID is empty")
        if not self.client_id:
            raise ZoomAuthError("ZOOM_CLIENT_ID is empty")
        if not self.client_secret:
            raise ZoomAuthError("ZOOM_CLIENT_SECRET is empty")

        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None
        self._cached: _CachedToken | None = None

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> ZoomAuth:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _basic_auth_header(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _token_is_fresh(self, *, now: datetime) -> bool:
        if self._cached is None:
            return False
        return now < (self._cached.expires_at - TOKEN_REFRESH_SKEW)

    def get_access_token(
        self, *, now: datetime | None = None, force_refresh: bool = False
    ) -> str:
        """Return a cached access token, refreshing at T-5m before expiry."""
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)

        if not force_refresh and self._token_is_fresh(now=moment):
            assert self._cached is not None
            return self._cached.token

        response = self._http.post(
            self.token_url,
            params={"grant_type": "account_credentials", "account_id": self.account_id},
            headers={"Authorization": self._basic_auth_header()},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ZoomAuthError(f"token exchange failed: {exc.response.status_code}") from exc

        body = response.json()
        token = body.get("access_token")
        expires_in = body.get("expires_in")
        if not token or not expires_in:
            raise ZoomAuthError("token response missing access_token/expires_in")

        # Zoom returns expires_in seconds from issuance, not an absolute timestamp.
        expires_at = moment + timedelta(seconds=int(expires_in))
        self._cached = _CachedToken(token=token, expires_at=expires_at)
        return token

    def clear_cache(self) -> None:
        """Drop the cached access token."""
        self._cached = None
