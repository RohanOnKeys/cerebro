"""CI run ledger helpers: upsert from GitHub payloads and explain failures."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import CiRun
from cerebro.github.api import GitHubAPI


def serialize_ci_run(run: CiRun) -> dict[str, Any]:
    """Serialize a CiRun row for tool responses."""
    return {
        "id": run.id,
        "org_id": run.org_id,
        "github_run_id": run.github_run_id,
        "owner": run.owner,
        "repo": run.repo,
        "workflow_name": run.workflow_name,
        "head_branch": run.head_branch,
        "head_sha": run.head_sha,
        "status": run.status,
        "conclusion": run.conclusion or "",
        "html_url": run.html_url,
        "event": run.event,
        "failure_summary": run.failure_summary or "",
        "created_at": run.created_at.isoformat() if run.created_at else "",
        "updated_at": run.updated_at.isoformat() if run.updated_at else "",
    }


def _parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def upsert_from_github(
    session: Session,
    *,
    org_id: str,
    owner: str,
    repo: str,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> CiRun:
    """Insert or update a CiRun from a GitHub workflow_run payload."""
    moment = now or datetime.now(UTC)
    github_run_id = str(payload.get("id", ""))
    if not github_run_id:
        raise ValueError("workflow run payload missing id")

    row = (
        session.query(CiRun)
        .filter(CiRun.org_id == org_id, CiRun.github_run_id == github_run_id)
        .first()
    )
    if row is None:
        row = CiRun(
            id=f"cirun_{uuid.uuid4().hex[:12]}",
            org_id=org_id,
            github_run_id=github_run_id,
            owner=owner,
            repo=repo,
            created_at=moment,
        )
        session.add(row)

    row.owner = owner
    row.repo = repo
    row.workflow_name = str(payload.get("name") or "")
    row.head_branch = str(payload.get("head_branch") or "")
    row.head_sha = str(payload.get("head_sha") or "")
    row.status = str(payload.get("status") or "")
    conclusion = payload.get("conclusion")
    row.conclusion = str(conclusion) if conclusion is not None else None
    row.html_url = str(payload.get("html_url") or "")
    row.event = str(payload.get("event") or "")
    row.updated_at = moment
    run_created = _parse_github_time(payload.get("created_at"))
    if run_created is not None and row.created_at is None:
        row.created_at = run_created
    session.flush()
    return row


def list_ci_runs_live(
    session: Session,
    api: GitHubAPI,
    *,
    org_id: str,
    owner: str,
    repo: str,
    branch: str | None = None,
    status: str | None = None,
    per_page: int = 30,
) -> list[CiRun]:
    """Fetch workflow runs from GitHub, upsert into the ledger, return rows."""
    payloads = api.list_workflow_runs(
        owner, repo, branch=branch, status=status, per_page=per_page
    )
    rows = [
        upsert_from_github(
            session, org_id=org_id, owner=owner, repo=repo, payload=payload
        )
        for payload in payloads
    ]
    session.commit()
    return rows


def explain_ci_failure(
    session: Session,
    api: GitHubAPI,
    *,
    org_id: str,
    owner: str,
    repo: str,
    run_id: int | str,
) -> dict[str, Any]:
    """Explain a failed (or failing) CI run using jobs/steps/annotations."""
    run_payload = api.get_workflow_run(owner, repo, run_id)
    row = upsert_from_github(
        session, org_id=org_id, owner=owner, repo=repo, payload=run_payload
    )

    jobs = api.list_jobs_for_run(owner, repo, run_id)
    failed_jobs: list[dict[str, Any]] = []
    for job in jobs:
        conclusion = (job.get("conclusion") or "").lower()
        job_status = (job.get("status") or "").lower()
        if conclusion not in {"failure", "timed_out", "cancelled"} and job_status != "failure":
            continue

        failed_steps = []
        for step in job.get("steps") or []:
            step_conclusion = (step.get("conclusion") or "").lower()
            if step_conclusion in {"failure", "timed_out", "cancelled"}:
                failed_steps.append(
                    {
                        "name": step.get("name") or "",
                        "number": step.get("number"),
                        "conclusion": step_conclusion,
                    }
                )

        annotations: list[dict[str, Any]] = []
        check_run_id = job.get("id")
        if check_run_id is not None:
            try:
                raw_annotations = api.list_annotations_for_check_run(
                    owner, repo, check_run_id
                )
            except Exception:  # noqa: BLE001 - annotations are best-effort
                raw_annotations = []
            for ann in raw_annotations:
                annotations.append(
                    {
                        "path": ann.get("path") or "",
                        "start_line": ann.get("start_line"),
                        "message": ann.get("message") or "",
                        "annotation_level": ann.get("annotation_level") or "",
                    }
                )

        failed_jobs.append(
            {
                "name": job.get("name") or "",
                "conclusion": conclusion or job_status,
                "html_url": job.get("html_url") or "",
                "failed_steps": failed_steps,
                "annotations": annotations,
            }
        )

    if not failed_jobs:
        summary = (
            f"Run {run_id} conclusion={run_payload.get('conclusion') or 'unknown'}; "
            "no failed jobs found."
        )
    else:
        parts = []
        for job in failed_jobs:
            step_names = ", ".join(step["name"] for step in job["failed_steps"]) or "unknown step"
            parts.append(f"{job['name']}: {step_names} ({job['conclusion']})")
        summary = "; ".join(parts)

    row.failure_summary = summary
    row.updated_at = datetime.now(UTC)
    session.commit()

    return {
        "run": serialize_ci_run(row),
        "failed_jobs": failed_jobs,
        "summary": summary,
    }
