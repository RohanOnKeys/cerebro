"""Unit tests for GitHub App auth (PEM → JWT → installation token cache)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cerebro.github.app_auth import (
    TOKEN_REFRESH_SKEW,
    GitHubAppAuth,
    GitHubAuthError,
    decode_private_key_pem,
)


@pytest.fixture
def rsa_pem_b64() -> str:
    """Generate a throwaway RSA PEM encoded as base64 for tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


def test_decode_private_key_pem_roundtrip(rsa_pem_b64):
    """Base64 PEM decodes to a PEM document."""
    pem = decode_private_key_pem(rsa_pem_b64)
    assert "BEGIN" in pem
    assert "PRIVATE KEY" in pem


def test_decode_private_key_pem_rejects_empty():
    """Empty key material raises GitHubAuthError."""
    with pytest.raises(GitHubAuthError, match="empty"):
        decode_private_key_pem("")


def test_make_jwt_is_rs256_with_app_iss(rsa_pem_b64):
    """JWT is RS256-signed and carries iss=app_id."""
    http = MagicMock()
    auth = GitHubAppAuth(
        app_id="12345",
        private_key_b64=rsa_pem_b64,
        installation_id="67890",
        http_client=http,
    )
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
    token = auth.make_jwt(now=now)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == "12345"
    assert claims["exp"] > claims["iat"]


def test_get_installation_token_caches_until_t_minus_5m(rsa_pem_b64):
    """Token is cached and reused until within 5 minutes of expiry."""
    http = MagicMock()
    expires_at = datetime(2026, 8, 11, 13, 0, 0, tzinfo=UTC)
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "token": "ghs_cached",
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    http.post.return_value = response

    auth = GitHubAppAuth(
        app_id="12345",
        private_key_b64=rsa_pem_b64,
        installation_id="67890",
        http_client=http,
    )

    t0 = expires_at - timedelta(minutes=30)
    assert auth.get_installation_token(now=t0) == "ghs_cached"
    assert http.post.call_count == 1

    t_fresh = expires_at - TOKEN_REFRESH_SKEW - timedelta(seconds=1)
    assert auth.get_installation_token(now=t_fresh) == "ghs_cached"
    assert http.post.call_count == 1

    response.json.return_value = {
        "token": "ghs_refreshed",
        "expires_at": (expires_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    t_refresh = expires_at - TOKEN_REFRESH_SKEW + timedelta(seconds=1)
    assert auth.get_installation_token(now=t_refresh) == "ghs_refreshed"
    assert http.post.call_count == 2


def test_force_refresh_bypasses_cache(rsa_pem_b64):
    """force_refresh exchanges a new installation token even if cache is fresh."""
    http = MagicMock()
    expires_at = datetime(2026, 8, 11, 13, 0, 0, tzinfo=UTC)
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "token": "ghs_one",
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    http.post.return_value = response

    auth = GitHubAppAuth(
        app_id="12345",
        private_key_b64=rsa_pem_b64,
        installation_id="67890",
        http_client=http,
    )
    now = expires_at - timedelta(minutes=30)
    auth.get_installation_token(now=now)
    response.json.return_value = {
        "token": "ghs_two",
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    assert auth.get_installation_token(now=now, force_refresh=True) == "ghs_two"
    assert http.post.call_count == 2


def test_missing_installation_id_raises(rsa_pem_b64):
    """Construction fails closed without an installation id."""
    with pytest.raises(GitHubAuthError, match="INSTALLATION"):
        GitHubAppAuth(
            app_id="12345",
            private_key_b64=rsa_pem_b64,
            installation_id="",
            http_client=MagicMock(),
        )
