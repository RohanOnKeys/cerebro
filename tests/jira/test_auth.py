"""Unit tests for Jira Basic auth."""

from __future__ import annotations

import base64

import pytest

from cerebro.jira.auth import JiraAuth, JiraAuthError


def test_basic_auth_header_is_base64_email_colon_token():
    auth = JiraAuth(
        base_url="https://acme.atlassian.net", email="bot@acme.com", api_token="s3cret"
    )
    header = auth.basic_auth_header()
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8")
    assert decoded == "bot@acme.com:s3cret"


def test_base_url_trailing_slash_stripped():
    auth = JiraAuth(
        base_url="https://acme.atlassian.net/", email="bot@acme.com", api_token="s3cret"
    )
    assert auth.base_url == "https://acme.atlassian.net"


def test_missing_base_url_raises():
    with pytest.raises(JiraAuthError, match="BASE_URL"):
        JiraAuth(base_url="", email="bot@acme.com", api_token="s3cret")


def test_missing_email_raises():
    with pytest.raises(JiraAuthError, match="EMAIL"):
        JiraAuth(base_url="https://acme.atlassian.net", email="", api_token="s3cret")


def test_missing_api_token_raises():
    with pytest.raises(JiraAuthError, match="API_TOKEN"):
        JiraAuth(base_url="https://acme.atlassian.net", email="bot@acme.com", api_token="")
