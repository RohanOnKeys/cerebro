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
