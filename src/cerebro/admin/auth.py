"""Auth gate for the Admin/Read API.

Deliberately simple: a single shared-secret bearer token, checked with a
constant-time comparison. This is meant to close the "anyone who can reach
the port can read the whole org's ledger" hole before first deploy, not to
be a full identity system — put real SSO in front of this (or replace this
dependency with one that validates a session from your SSO provider) before
this dashboard is handed to more than a couple of trusted admins.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cerebro.config import settings

_bearer = HTTPBearer(auto_error=False)


def require_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if not settings.admin_api_token:
        # Fail closed: an unset token means the route is unreachable, not
        # unprotected. Set ADMIN_API_TOKEN before deploying this router.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin API is not configured (ADMIN_API_TOKEN unset)",
        )
    if credentials is None or not hmac.compare_digest(
        credentials.credentials, settings.admin_api_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
