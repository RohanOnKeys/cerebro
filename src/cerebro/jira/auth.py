"""Jira Cloud authentication: a single shared API token, Basic auth.

No token exchange or expiry, unlike GitHub's App JWT dance, an API token
is a long-lived credential the account holder rotates by hand. Kept as a
class (rather than a bare function) purely for consistency with the other
integrations and to give tests something to construct and inject.
"""

from __future__ import annotations

import base64

from cerebro.config import settings

JIRA_API_BASE = "/rest/api/3"


class JiraAuthError(RuntimeError):
    """Raised when Jira credentials are missing or malformed."""


class JiraAuth:
    """Holds Jira Cloud Basic-auth credentials and the org's base URL."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.jira_base_url).rstrip(
            "/"
        )
        self.email = (email if email is not None else settings.jira_email).strip()
        self.api_token = (api_token if api_token is not None else settings.jira_api_token).strip()

        if not self.base_url:
            raise JiraAuthError("JIRA_BASE_URL is empty")
        if not self.email:
            raise JiraAuthError("JIRA_EMAIL is empty")
        if not self.api_token:
            raise JiraAuthError("JIRA_API_TOKEN is empty")

    def basic_auth_header(self) -> str:
        """Return the `Authorization: Basic <...>` value for email:token."""
        raw = f"{self.email}:{self.api_token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")
