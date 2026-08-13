"""Jira Cloud REST v3 client: create/read issues."""

from __future__ import annotations

from typing import Any

import httpx

from cerebro.jira.auth import JIRA_API_BASE, JiraAuth


class JiraAPIError(RuntimeError):
    """Raised when a Jira API call fails."""


def _text_to_adf(text: str) -> dict[str, Any]:
    """Wrap plain text as a single-paragraph Atlassian Document Format node.

    Jira Cloud's v3 issue API requires `description` as ADF, not a plain
    string; this is the minimal shape for one paragraph of text.
    """
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}] if text else [],
            }
        ],
    }


class JiraAPI:
    """Thin wrapper over Jira Cloud's REST v3 API, Basic-auth authenticated."""

    def __init__(
        self,
        auth: JiraAuth,
        *,
        http_client: httpx.Client | None = None,
        api_base: str | None = None,
    ) -> None:
        self.auth = auth
        self.api_base = (api_base or f"{auth.base_url}{JIRA_API_BASE}").rstrip("/")
        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> JiraAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.auth.basic_auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

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
            raise JiraAPIError(f"{method} {path} failed: {exc.response.status_code}") from exc
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def create_issue(
        self,
        project_key: str,
        *,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a Jira issue; returns the API's {id, key, self} payload."""
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = _text_to_adf(description)
        if labels:
            fields["labels"] = labels
        result = self._request("POST", "/issue", json_body={"fields": fields})
        if not isinstance(result, dict):
            raise JiraAPIError("unexpected create issue payload")
        return result

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Fetch one issue by key (e.g. 'PROJ-123')."""
        result = self._request("GET", f"/issue/{issue_key}")
        if not isinstance(result, dict):
            raise JiraAPIError("unexpected get issue payload")
        return result
