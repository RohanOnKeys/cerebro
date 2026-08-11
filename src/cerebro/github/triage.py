"""CI failure triage: log slice, fingerprint, flake budget, LLM hook."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from cerebro.config import settings
from cerebro.db.models import CiFailure, CiRun, Principal, Task
from cerebro.github.api import GitHubAPI
from cerebro.github.webhook import CIEvent, parse_task_number_from_branch
from cerebro.services import tasks as tasks_service

# Strip timestamps, absolute paths, and PIDs before fingerprinting.
_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|/)(?:[^\s:]+[/\\])+[^\s:]+")
_PID_RE = re.compile(r"\bpid[=:\s]+\d+\b", re.IGNORECASE)
_PID_BARE_RE = re.compile(r"\b\[\d{3,}\]\b")

LOG_SLICE_CHARS = 4000

TriageFn = Callable[[str, dict[str, Any]], dict[str, Any]]


def slice_log(text: str, *, limit: int = LOG_SLICE_CHARS) -> str:
    """Keep the tail of a log blob (failures usually land at the end)."""
    raw = text or ""
    if len(raw) <= limit:
        return raw
    return raw[-limit:]


def normalize_for_fingerprint(text: str) -> str:
    """Strip volatile tokens (timestamps, paths, PIDs) from a log slice."""
    out = slice_log(text)
    out = _TS_RE.sub("<TS>", out)
    out = _PATH_RE.sub("<PATH>", out)
    out = _PID_RE.sub("pid=<PID>", out)
    out = _PID_BARE_RE.sub("[<PID>]", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def fingerprint_log(text: str) -> str:
    """Stable sha256 fingerprint of a normalized log slice."""
    normalized = normalize_for_fingerprint(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def default_llm_triage(log_slice: str, context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic triage stub (tests inject a mockable hook)."""
    lines = [line.strip() for line in log_slice.splitlines() if line.strip()]
    hint = lines[-1] if lines else "unknown failure"
    return {
        "category": "unknown",
        "summary": hint[:240],
        "likely_flake": "flaky" in log_slice.lower() or "timeout" in log_slice.lower(),
        "context": {
            "run_id": context.get("run_id"),
            "workflow": context.get("workflow_name"),
        },
    }


def lookup_ci_failure(
    session: Session, *, org_id: str, fingerprint: str
) -> CiFailure | None:
    """Fetch an existing fingerprinted failure row."""
    return (
        session.query(CiFailure)
        .filter(CiFailure.org_id == org_id, CiFailure.fingerprint == fingerprint)
        .first()
    )


def link_task_for_run(session: Session, ci_run: CiRun, *, head_branch: str) -> str | None:
    """Link ci_runs.task_id from branch naming (task-12 / task/12)."""
    if ci_run.task_id:
        return ci_run.task_id
    number = parse_task_number_from_branch(head_branch)
    if number is None:
        return None
    task = tasks_service.get_task_by_number(session, org_id=ci_run.org_id, number=number)
    if task is None:
        return None
    ci_run.task_id = task.id
    session.flush()
    return task.id


def block_task_on_red_build(
    session: Session, *, ci_run: CiRun, event: CIEvent
) -> dict[str, Any] | None:
    """Red build on a linked task branch → mark task blocked (lead nudge path)."""
    if not ci_run.task_id:
        return None
    task = session.query(Task).filter(Task.id == ci_run.task_id).first()
    if task is None:
        return None
    actor = (
        session.query(Principal)
        .filter(Principal.org_id == ci_run.org_id)
        .order_by(Principal.created_at.asc())
        .first()
    )
    if actor is None:
        return None
    reason = (
        f"CI red on {event.head_branch}: run {event.run_id} "
        f"({event.workflow_name}) {event.html_url}"
    )
    blocked = tasks_service.block_task(
        session,
        org_id=task.org_id,
        number=task.number,
        principal=actor,
        reason=reason,
    )
    if blocked is None:
        return None
    return {
        "task_id": blocked.id,
        "number": blocked.number,
        "status": blocked.status,
        "blocked_reason": blocked.blocked_reason,
    }


def _window_hours() -> int:
    return int(settings.ci_flake_window_hours or 24)


def _budget() -> int:
    return int(settings.ci_flake_budget or 3)


def handle_failed_run(
    session: Session,
    *,
    event: CIEvent,
    ci_run: CiRun,
    log_text: str = "",
    api: GitHubAPI | None = None,
    triage_fn: TriageFn | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fingerprint failure, apply flake budget (T1 auto-rerun max N/24h)."""
    moment = now or datetime.now(UTC)
    sample = slice_log(log_text or ci_run.failure_summary or event.workflow_name)
    fp = fingerprint_log(sample)
    org_id = ci_run.org_id
    triage = (triage_fn or default_llm_triage)(
        sample,
        {
            "run_id": event.run_id,
            "workflow_name": event.workflow_name,
            "owner": event.owner,
            "repo": event.repo,
        },
    )

    row = lookup_ci_failure(session, org_id=org_id, fingerprint=fp)
    window = timedelta(hours=_window_hours())
    if row is None:
        row = CiFailure(
            id=f"cifail_{uuid.uuid4().hex[:12]}",
            org_id=org_id,
            fingerprint=fp,
            owner=event.owner,
            repo=event.repo,
            sample_log=sample,
            triage_json=json.dumps(triage),
            rerun_count_window=0,
            window_started_at=moment,
            last_seen_at=moment,
            created_at=moment,
        )
        session.add(row)
    else:
        started = row.window_started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        if started is None or moment - started >= window:
            row.rerun_count_window = 0
            row.window_started_at = moment
            row.issue_url = None
        row.sample_log = sample
        row.triage_json = json.dumps(triage)
        row.last_seen_at = moment

    budget = _budget()
    action = "stop"
    issue_url = row.issue_url or ""

    if row.rerun_count_window < budget:
        row.rerun_count_window += 1
        action = "rerun"
        if api is not None:
            api.rerun_workflow(event.owner, event.repo, event.run_id)
    else:
        action = "open_issue"
        if api is not None and not row.issue_url:
            issue = api.create_issue(
                event.owner,
                event.repo,
                title=f"[cerebro] CI flake budget exhausted: {event.workflow_name}",
                body=(
                    f"Fingerprint `{fp}` hit {budget} auto-reruns in {_window_hours()}h.\n\n"
                    f"Run: {event.html_url}\n\n```\n{sample[:1500]}\n```\n\n"
                    f"Triage: {json.dumps(triage)}"
                ),
                labels=["ci-flake", "cerebro"],
            )
            issue_url = str(issue.get("html_url") or "")
            row.issue_url = issue_url

    session.flush()
    return {
        "fingerprint": fp,
        "action": action,
        "rerun_count_window": row.rerun_count_window,
        "budget": budget,
        "issue_url": issue_url,
        "triage": triage,
        "ci_failure_id": row.id,
    }
