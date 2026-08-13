"""Unit tests for the Zoom API wrapper."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest

from cerebro.zoom.api import ZoomAPI, ZoomAPIError


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.get_access_token.return_value = "tok_test"
    return fake


def test_create_meeting_sends_scheduled_type_and_bearer_token(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 201
    response.content = b"{}"
    response.json.return_value = {
        "id": 123456789,
        "join_url": "https://zoom.us/j/123456789",
        "start_url": "https://zoom.us/s/123456789",
    }
    http.request.return_value = response

    api = ZoomAPI(auth, http_client=http)
    result = api.create_meeting(
        "dev@acme.com",
        topic="Standup",
        start_time=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        duration_minutes=30,
    )

    assert result["meeting_id"] == 123456789
    assert result["join_url"] == "https://zoom.us/j/123456789"

    call = http.request.call_args
    assert call.args[0] == "POST"
    assert call.args[1].endswith("/users/dev@acme.com/meetings")
    assert call.kwargs["headers"]["Authorization"] == "Bearer tok_test"
    body = call.kwargs["json"]
    assert body["type"] == 2
    assert body["duration"] == 30


def test_create_meeting_http_error_raises_api_error(auth):
    http = MagicMock()
    request = httpx.Request("POST", "https://x/meetings")
    error_response = httpx.Response(404, request=request)
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad", request=request, response=error_response
    )
    http.request.return_value = response

    api = ZoomAPI(auth, http_client=http)
    with pytest.raises(ZoomAPIError):
        api.create_meeting(
            "dev@acme.com",
            topic="x",
            start_time=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
            duration_minutes=30,
        )


def test_delete_meeting_calls_delete(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 204
    response.content = b""
    http.request.return_value = response

    api = ZoomAPI(auth, http_client=http)
    api.delete_meeting("123456789")

    call = http.request.call_args
    assert call.args[0] == "DELETE"
    assert call.args[1].endswith("/meetings/123456789")
