"""Unit tests for the Google Calendar API wrapper."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest

from cerebro.gcal.api import GoogleCalendarAPI, GoogleCalendarAPIError


@pytest.fixture
def auth():
    fake = MagicMock()
    fake.get_access_token.return_value = "tok_test"
    return fake


def test_create_event_sends_conference_data_and_bearer_token(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 200
    response.content = b"{}"
    response.json.return_value = {
        "id": "evt_1",
        "htmlLink": "https://calendar.google.com/evt_1",
        "conferenceData": {
            "entryPoints": [
                {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"}
            ]
        },
    }
    http.request.return_value = response

    api = GoogleCalendarAPI(auth, http_client=http)
    result = api.create_event(
        "cal_1",
        summary="Standup",
        start=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        end=datetime(2026, 8, 14, 9, 30, tzinfo=UTC),
        attendee_emails=["dev@acme.com"],
    )

    assert result["event_id"] == "evt_1"
    assert result["meet_link"] == "https://meet.google.com/abc-defg-hij"

    call = http.request.call_args
    assert call.args[0] == "POST"
    assert call.kwargs["headers"]["Authorization"] == "Bearer tok_test"
    assert call.kwargs["params"]["conferenceDataVersion"] == 1
    body = call.kwargs["json"]
    assert body["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == (
        "hangoutsMeet"
    )
    assert body["attendees"] == [{"email": "dev@acme.com"}]


def test_create_event_without_meet_link_skips_conference_data(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 200
    response.content = b"{}"
    response.json.return_value = {"id": "evt_2", "htmlLink": "https://x"}
    http.request.return_value = response

    api = GoogleCalendarAPI(auth, http_client=http)
    result = api.create_event(
        "cal_1",
        summary="Standup",
        start=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        end=datetime(2026, 8, 14, 9, 30, tzinfo=UTC),
        create_meet_link=False,
    )

    assert result["meet_link"] == ""
    call = http.request.call_args
    assert "conferenceData" not in call.kwargs["json"]
    assert call.kwargs["params"] == {}


def test_create_event_http_error_raises_api_error(auth):
    http = MagicMock()
    request = httpx.Request("POST", "https://x/events")
    error_response = httpx.Response(403, request=request)
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad", request=request, response=error_response
    )
    http.request.return_value = response

    api = GoogleCalendarAPI(auth, http_client=http)
    with pytest.raises(GoogleCalendarAPIError):
        api.create_event(
            "cal_1",
            summary="x",
            start=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
            end=datetime(2026, 8, 14, 9, 30, tzinfo=UTC),
        )


def test_delete_event_calls_delete(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 204
    response.content = b""
    http.request.return_value = response

    api = GoogleCalendarAPI(auth, http_client=http)
    api.delete_event("cal_1", "evt_1")

    call = http.request.call_args
    assert call.args[0] == "DELETE"
    assert call.args[1].endswith("/events/evt_1")


def test_free_busy_flattens_and_sorts_intervals(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 200
    response.content = b"{}"
    response.json.return_value = {
        "calendars": {
            "cal_1": {
                "busy": [
                    {"start": "2026-08-14T11:00:00+00:00", "end": "2026-08-14T12:00:00+00:00"}
                ]
            },
            "dev@acme.com": {
                "busy": [
                    {"start": "2026-08-14T09:00:00+00:00", "end": "2026-08-14T09:30:00+00:00"}
                ]
            },
        }
    }
    http.request.return_value = response

    api = GoogleCalendarAPI(auth, http_client=http)
    busy = api.free_busy(
        "cal_1",
        ["dev@acme.com"],
        time_min=datetime(2026, 8, 14, 0, 0, tzinfo=UTC),
        time_max=datetime(2026, 8, 15, 0, 0, tzinfo=UTC),
    )

    assert len(busy) == 2
    assert busy[0][0] < busy[1][0]
    assert busy[0] == (
        datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        datetime(2026, 8, 14, 9, 30, tzinfo=UTC),
    )
