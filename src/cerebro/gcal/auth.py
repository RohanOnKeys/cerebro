"""Google Calendar auth: service-account JWT-bearer -> access token.

One shared org calendar via a single service-account credential, not
per-principal OAuth. The calendar must already be shared with the
service account's client_email as an editor (a bare service account
has no calendar of its own); GCAL_CALENDAR_ID must be that calendar's
real id, not "primary".
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from cerebro.config import settings

DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
JWT_LIFETIME = timedelta(hours=1)
TOKEN_REFRESH_SKEW = timedelta(minutes=5)


class GoogleCalendarAuthError(RuntimeError):
    """Raised when Google Calendar credentials or token exchange fail."""


def decode_service_account_json(service_account_json_b64: str) -> dict[str, Any]:
    """Decode a base64-encoded service-account JSON key."""
    raw = (service_account_json_b64 or "").strip()
    if not raw:
        raise GoogleCalendarAuthError("GCAL_SERVICE_ACCOUNT_JSON_B64 is empty")
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise GoogleCalendarAuthError(
            "GCAL_SERVICE_ACCOUNT_JSON_B64 is not valid base64 JSON"
        ) from exc
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise GoogleCalendarAuthError("decoded key is not valid JSON") from exc
    if not isinstance(data, dict):
        raise GoogleCalendarAuthError("decoded key is not a JSON object")
    return data


@dataclass
class _CachedToken:
    token: str
    expires_at: datetime


class GoogleCalendarAuth:
    """Mint and cache Google Calendar access tokens via a service account.

    Flow: load service-account JSON -> sign a self-contained JWT
    (iss=client_email, scope=calendar) -> exchange it for an access
    token at Google's token endpoint -> cache until refresh skew (T-5m).
    """

    def __init__(
        self,
        *,
        service_account_json_b64: str | None = None,
        impersonate_subject: str | None = None,
        http_client: httpx.Client | None = None,
        token_uri: str | None = None,
    ) -> None:
        raw_json = (
            service_account_json_b64
            if service_account_json_b64 is not None
            else settings.gcal_service_account_json_b64
        )
        data = decode_service_account_json(raw_json)

        self.client_email = str(data.get("client_email") or "").strip()
        self._private_key = str(data.get("private_key") or "").strip()
        self.token_uri = (token_uri or data.get("token_uri") or DEFAULT_TOKEN_URI).strip()
        self.impersonate_subject = (
            impersonate_subject
            if impersonate_subject is not None
            else settings.gcal_impersonate_subject
        ).strip()

        if not self.client_email:
            raise GoogleCalendarAuthError("service account JSON is missing client_email")
        if not self._private_key:
            raise GoogleCalendarAuthError("service account JSON is missing private_key")

        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None
        self._cached: _CachedToken | None = None

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> GoogleCalendarAuth:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def make_jwt(self, *, now: datetime | None = None) -> str:
        """Sign an RS256 JWT asserting this service account, scoped to Calendar."""
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        iat = int(moment.timestamp())
        exp = int((moment + JWT_LIFETIME).timestamp())
        payload: dict[str, Any] = {
            "iss": self.client_email,
            "scope": CALENDAR_SCOPE,
            "aud": self.token_uri,
            "iat": iat,
            "exp": exp,
        }
        if self.impersonate_subject:
            payload["sub"] = self.impersonate_subject
        return jwt.encode(payload, self._private_key, algorithm="RS256")

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

        assertion = self.make_jwt(now=moment)
        response = self._http.post(
            self.token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GoogleCalendarAuthError(
                f"token exchange failed: {exc.response.status_code}"
            ) from exc

        body = response.json()
        token = body.get("access_token")
        expires_in = body.get("expires_in")
        if not token or not expires_in:
            raise GoogleCalendarAuthError(
                "token response missing access_token/expires_in"
            )

        expires_at = moment + timedelta(seconds=int(expires_in))
        self._cached = _CachedToken(token=token, expires_at=expires_at)
        return token

    def clear_cache(self) -> None:
        """Drop the cached access token."""
        self._cached = None
