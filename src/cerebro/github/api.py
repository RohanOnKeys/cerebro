"""GitHub REST API T0 (read-only) helpers for CI workflow runs."""

from __future__ import annotations

from typing import Any

import httpx

from cerebro.github.app_auth import GITHUB_API_BASE, GitHubAppAuth


class GitHubAPIError(RuntimeError):
    """Raised when a GitHub API read fails."""


class GitHubAPI:
    """Read-only GitHub Actions client authenticated via GitHub App tokens."""

    def __init__(
        self,
        auth: GitHubAppAuth,
        *,
        http_client: httpx.Client | None = None,
        api_base: str = GITHUB_API_BASE,
    ) -> None:
        self.auth = auth
        self.api_base = api_base.rstrip("/")
        self._http = http_client or httpx.Client(timeout=30.0)
        self._owns_http = http_client is None

    def close(self) -> None:
        """Close the owned HTTP client (does not close auth's client)."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> GitHubAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        token = self.auth.get_installation_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self._http.get(
            f"{self.api_base}{path}",
            headers=self._headers(),
            params=params or {},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubAPIError(
                f"GET {path} failed: {exc.response.status_code}"
            ) from exc
        return response.json()

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        *,
        branch: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List recent workflow runs for a repository (T0 read)."""
        params: dict[str, Any] = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status
        body = self._get(f"/repos/{owner}/{repo}/actions/runs", params=params)
        runs = body.get("workflow_runs") if isinstance(body, dict) else None
        return list(runs or [])

    def get_workflow_run(self, owner: str, repo: str, run_id: int | str) -> dict[str, Any]:
        """Fetch one workflow run by id (T0 read)."""
        body = self._get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        if not isinstance(body, dict):
            raise GitHubAPIError("unexpected workflow run payload")
        return body

    def list_jobs_for_run(
        self, owner: str, repo: str, run_id: int | str, *, per_page: int = 100
    ) -> list[dict[str, Any]]:
        """List jobs (and steps) for a workflow run (T0 read)."""
        body = self._get(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            params={"per_page": per_page},
        )
        jobs = body.get("jobs") if isinstance(body, dict) else None
        return list(jobs or [])

    def list_annotations_for_check_run(
        self, owner: str, repo: str, check_run_id: int | str
    ) -> list[dict[str, Any]]:
        """List annotations on a check run (T0 read; used for failure detail)."""
        body = self._get(
            f"/repos/{owner}/{repo}/check-runs/{check_run_id}/annotations"
        )
        if isinstance(body, list):
            return list(body)
        return []

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
            raise GitHubAPIError(
                f"{method} {path} failed: {exc.response.status_code}"
            ) from exc
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def rerun_workflow(self, owner: str, repo: str, run_id: int | str) -> dict[str, Any]:
        """Re-run all jobs for a workflow run."""
        return self._request(
            "POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun"
        )

    def dispatch_workflow(
        self,
        owner: str,
        repo: str,
        workflow_id: str,
        *,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Trigger workflow_dispatch for a workflow file or id."""
        body: dict[str, Any] = {"ref": ref}
        if inputs:
            body["inputs"] = inputs
        return self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            json_body=body,
        )

    def cancel_run(self, owner: str, repo: str, run_id: int | str) -> dict[str, Any]:
        """Cancel an in-progress workflow run."""
        return self._request(
            "POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel"
        )

    def create_issue(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Open a GitHub issue (used when flake budget is exhausted)."""
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        result = self._request(
            "POST", f"/repos/{owner}/{repo}/issues", json_body=payload
        )
        if not isinstance(result, dict):
            raise GitHubAPIError("unexpected create issue payload")
        return result
