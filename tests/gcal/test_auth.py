"""Unit tests for Google Calendar service-account auth (JWT-bearer -> token)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cerebro.gcal.auth import (
    TOKEN_REFRESH_SKEW,
    GoogleCalendarAuth,
    GoogleCalendarAuthError,
    decode_service_account_json,
)


@pytest.fixture
def service_account_json_b64() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    payload = {
        "client_email": "bot@acme.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def test_decode_service_account_json_roundtrip(service_account_json_b64):
    data = decode_service_account_json(service_account_json_b64)
    assert data["client_email"] == "bot@acme.iam.gserviceaccount.com"


def test_decode_service_account_json_rejects_empty():
    with pytest.raises(GoogleCalendarAuthError, match="empty"):
        decode_service_account_json("")


def test_make_jwt_is_rs256_with_calendar_scope(service_account_json_b64):
    http = MagicMock()
    auth = GoogleCalendarAuth(
        service_account_json_b64=service_account_json_b64, http_client=http
    )
    now = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
    token = auth.make_jwt(now=now)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == "bot@acme.iam.gserviceaccount.com"
    assert claims["scope"] == "https://www.googleapis.com/auth/calendar"
    assert claims["exp"] > claims["iat"]
    assert "sub" not in claims


def test_make_jwt_includes_sub_when_impersonating(service_account_json_b64):
    http = MagicMock()
    auth = GoogleCalendarAuth(
        service_account_json_b64=service_account_json_b64,
        impersonate_subject="team@acme.com",
        http_client=http,
    )
    token = auth.make_jwt()
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["sub"] == "team@acme.com"


def test_get_access_token_caches_until_t_minus_5m(service_account_json_b64):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"access_token": "tok_cached", "expires_in": 3600}
    http.post.return_value = response

    auth = GoogleCalendarAuth(
        service_account_json_b64=service_account_json_b64, http_client=http
    )
    t0 = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
    assert auth.get_access_token(now=t0) == "tok_cached"
    assert http.post.call_count == 1

    t_fresh = t0 + timedelta(minutes=30)
    assert auth.get_access_token(now=t_fresh) == "tok_cached"
    assert http.post.call_count == 1

    response.json.return_value = {"access_token": "tok_refreshed", "expires_in": 3600}
    t_refresh = t0 + timedelta(hours=1) - TOKEN_REFRESH_SKEW + timedelta(seconds=1)
    assert auth.get_access_token(now=t_refresh) == "tok_refreshed"
    assert http.post.call_count == 2


def test_force_refresh_bypasses_cache(service_account_json_b64):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"access_token": "tok_one", "expires_in": 3600}
    http.post.return_value = response

    auth = GoogleCalendarAuth(
        service_account_json_b64=service_account_json_b64, http_client=http
    )
    now = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
    auth.get_access_token(now=now)
    response.json.return_value = {"access_token": "tok_two", "expires_in": 3600}
    assert auth.get_access_token(now=now, force_refresh=True) == "tok_two"
    assert http.post.call_count == 2


def test_missing_client_email_raises():
    payload = {"private_key": "x"}
    b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    with pytest.raises(GoogleCalendarAuthError, match="client_email"):
        GoogleCalendarAuth(service_account_json_b64=b64, http_client=MagicMock())
