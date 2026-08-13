"""Zoom REST v2 client: create/delete meetings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from cerebro.zoom.auth import ZoomAuth

API_BASE = "https://api.zoom.us/v2"

# type=2 is a scheduled meeting (as opposed to instant/recurring).
SCHEDULED_MEETING_TYPE = 2


class ZoomAPIError(RuntimeError):
    """Raised when a Zoom API call fails."""


class ZoomAPI:
    """Thin wrapper over the Zoom v2 API, Server-to-Server OAuth authenticated."""

    def __init__(
        self,
        auth: ZoomAuth,
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

    def __enter__(self) -> ZoomAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        token = self.auth.get_access_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        response = self._http.request(
            method,
            f"{self.api_base}{path}",
            headers=self._headers(),
            json=json_body,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ZoomAPIError(f"{method} {path} failed: {exc.response.status_code}") from exc
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def create_meeting(
        self,
        user_id: str,
        *,
        topic: str,
        start_time: datetime,
        duration_minutes: int,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """Create a scheduled Zoom meeting; returns id/join_url/start_url."""
        body = {
            "topic": topic,
            "type": SCHEDULED_MEETING_TYPE,
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration": duration_minutes,
            "timezone": timezone,
            "settings": {"join_before_host": True, "waiting_room": False},
        }
        result = self._request("POST", f"/users/{user_id}/meetings", json_body=body)
        if not isinstance(result, dict):
            raise ZoomAPIError("unexpected create meeting payload")
        return {
            "meeting_id": result.get("id"),
            "join_url": result.get("join_url", ""),
            "start_url": result.get("start_url", ""),
        }

    def delete_meeting(self, meeting_id: str) -> None:
        """Delete/cancel a scheduled Zoom meeting."""
        self._request("DELETE", f"/meetings/{meeting_id}")
