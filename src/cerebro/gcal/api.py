"""Google Calendar REST v3 client: create/delete events, free/busy queries."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Sequence

import httpx

from cerebro.gcal.auth import GoogleCalendarAuth

API_BASE = "https://www.googleapis.com"


class GoogleCalendarAPIError(RuntimeError):
    """Raised when a Google Calendar API call fails."""


def _rfc3339(moment: datetime) -> str:
    return moment.isoformat()


class GoogleCalendarAPI:
    """Thin wrapper over the Google Calendar v3 API."""

    def __init__(
        self,
        auth: GoogleCalendarAuth,
        *,
        http_client: httpx.Client | None = None,
        api_base: str = API_BASE,
    ) -> None:
        self.auth = auth
        self.api_base = api_base.rstrip("/")
        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None

    def close(self) -> None:
        """Close the owned HTTP client (does not close auth's client)."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> GoogleCalendarAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        token = self.auth.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        response = self._http.request(
            method,
            f"{self.api_base}{path}",
            headers=self._headers(),
            params=params or {},
            json=json_body,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GoogleCalendarAPIError(
                f"{method} {path} failed: {exc.response.status_code}"
            ) from exc
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def create_event(
        self,
        calendar_id: str,
        *,
        summary: str,
        start: datetime,
        end: datetime,
        attendee_emails: Sequence[str] = (),
        create_meet_link: bool = True,
    ) -> dict[str, Any]:
        """Create a calendar event, optionally with an auto-generated Meet link."""
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": _rfc3339(start)},
            "end": {"dateTime": _rfc3339(end)},
            "attendees": [{"email": email} for email in attendee_emails],
        }
        params: dict[str, Any] = {}
        if create_meet_link:
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": uuid.uuid4().hex,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
            params["conferenceDataVersion"] = 1

        result = self._request(
            "POST",
            f"/calendar/v3/calendars/{calendar_id}/events",
            params=params,
            json_body=body,
        )
        if not isinstance(result, dict):
            raise GoogleCalendarAPIError("unexpected create event payload")

        meet_link = ""
        entry_points = ((result.get("conferenceData") or {}).get("entryPoints")) or []
        for entry in entry_points:
            if entry.get("entryPointType") == "video":
                meet_link = str(entry.get("uri") or "")
                break

        return {
            "event_id": result.get("id"),
            "meet_link": meet_link,
            "html_link": result.get("htmlLink", ""),
        }

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete a calendar event."""
        self._request("DELETE", f"/calendar/v3/calendars/{calendar_id}/events/{event_id}")

    def free_busy(
        self,
        calendar_id: str,
        emails: Sequence[str],
        *,
        time_min: datetime,
        time_max: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """Query free/busy intervals across a calendar plus attendee emails."""
        items = [{"id": calendar_id}, *[{"id": email} for email in emails]]
        body = {
            "timeMin": _rfc3339(time_min),
            "timeMax": _rfc3339(time_max),
            "items": items,
        }
        result = self._request("POST", "/calendar/v3/freeBusy", json_body=body)
        if not isinstance(result, dict):
            raise GoogleCalendarAPIError("unexpected freeBusy payload")

        calendars = result.get("calendars") or {}
        busy: list[tuple[datetime, datetime]] = []
        for entry in calendars.values():
            for interval in entry.get("busy") or []:
                start = interval.get("start")
                end = interval.get("end")
                if start and end:
                    busy.append((datetime.fromisoformat(start), datetime.fromisoformat(end)))
        busy.sort(key=lambda pair: pair[0])
        return busy
