"""Unit tests for Zoom Server-to-Server OAuth auth."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from cerebro.zoom.auth import TOKEN_REFRESH_SKEW, ZoomAuth, ZoomAuthError


def test_get_access_token_sends_basic_auth_and_account_credentials_grant():
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"access_token": "zoom_tok", "expires_in": 3600}
    http.post.return_value = response

    auth = ZoomAuth(
        account_id="acct_1", client_id="cid", client_secret="csecret", http_client=http
    )
    token = auth.get_access_token(now=datetime(2026, 8, 13, 12, 0, tzinfo=UTC))

    assert token == "zoom_tok"
    call = http.post.call_args
    assert call.args[0] == "https://zoom.us/oauth/token"
    assert call.kwargs["params"] == {
        "grant_type": "account_credentials",
        "account_id": "acct_1",
    }
    expected_header = "Basic " + base64.b64encode(b"cid:csecret").decode("ascii")
    assert call.kwargs["headers"]["Authorization"] == expected_header


def test_get_access_token_caches_using_expires_in_seconds():
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"access_token": "tok_cached", "expires_in": 3600}
    http.post.return_value = response

    auth = ZoomAuth(
        account_id="acct_1", client_id="cid", client_secret="csecret", http_client=http
    )
    t0 = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    assert auth.get_access_token(now=t0) == "tok_cached"
    assert http.post.call_count == 1

    t_fresh = t0 + timedelta(minutes=30)
    assert auth.get_access_token(now=t_fresh) == "tok_cached"
    assert http.post.call_count == 1

    response.json.return_value = {"access_token": "tok_refreshed", "expires_in": 3600}
    t_refresh = t0 + timedelta(hours=1) - TOKEN_REFRESH_SKEW + timedelta(seconds=1)
    assert auth.get_access_token(now=t_refresh) == "tok_refreshed"
    assert http.post.call_count == 2


def test_force_refresh_bypasses_cache():
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"access_token": "tok_one", "expires_in": 3600}
    http.post.return_value = response

    auth = ZoomAuth(
        account_id="acct_1", client_id="cid", client_secret="csecret", http_client=http
    )
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    auth.get_access_token(now=now)
    response.json.return_value = {"access_token": "tok_two", "expires_in": 3600}
    assert auth.get_access_token(now=now, force_refresh=True) == "tok_two"
    assert http.post.call_count == 2


def test_missing_account_id_raises():
    with pytest.raises(ZoomAuthError, match="ACCOUNT_ID"):
        ZoomAuth(account_id="", client_id="cid", client_secret="csecret", http_client=MagicMock())


def test_missing_client_secret_raises():
    with pytest.raises(ZoomAuthError, match="CLIENT_SECRET"):
        ZoomAuth(account_id="acct_1", client_id="cid", client_secret="", http_client=MagicMock())
