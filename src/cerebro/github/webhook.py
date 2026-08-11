"""GitHub webhook: signature verify + CIEvent normalizer + FastAPI route."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Request

from cerebro.config import settings
from cerebro.db.session import SessionLocal

router = APIRouter()

TASK_BRANCH_RE = re.compile(r"(?:^|/)(?:task[-/])(\d+)(?:$|/)", re.IGNORECASE)


@dataclass(frozen=True)
class CIEvent:
    """Normalized workflow_run webhook payload."""

    action: str
    owner: str
    repo: str
    run_id: str
    status: str
    conclusion: str
    head_branch: str
    head_sha: str
    workflow_name: str
    html_url: str
    event: str
    raw_run: dict[str, Any]


class WebhookSignatureError(ValueError):
    """Raised when X-Hub-Signature-256 does not match the body."""


def verify_signature(body: bytes, signature_header: str | None, secret: str) -> None:
    """Verify GitHub HMAC-SHA256 webhook signature (sha256=<hex>)."""
    if not secret:
        raise WebhookSignatureError("webhook secret not configured")
    if not signature_header or not signature_header.startswith("sha256="):
        raise WebhookSignatureError("missing or malformed signature")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, received):
        raise WebhookSignatureError("signature mismatch")


def normalize_workflow_run(payload: dict[str, Any]) -> CIEvent | None:
    """Normalize a workflow_run webhook JSON body into CIEvent."""
    if payload.get("workflow_run") is None and "workflow_run" not in payload:
        return None
    run = payload.get("workflow_run") or {}
    repo = payload.get("repository") or {}
    full_name = str(repo.get("full_name") or "")
    if "/" in full_name:
        owner, name = full_name.split("/", 1)
    else:
        owner = str((repo.get("owner") or {}).get("login") or "")
        name = str(repo.get("name") or "")
    run_id = run.get("id")
    if run_id is None:
        return None
    return CIEvent(
        action=str(payload.get("action") or ""),
        owner=owner,
        repo=name,
        run_id=str(run_id),
        status=str(run.get("status") or ""),
        conclusion=str(run.get("conclusion") or ""),
        head_branch=str(run.get("head_branch") or ""),
        head_sha=str(run.get("head_sha") or ""),
        workflow_name=str(run.get("name") or ""),
        html_url=str(run.get("html_url") or ""),
        event=str(run.get("event") or ""),
        raw_run=dict(run),
    )


def parse_task_number_from_branch(branch: str) -> int | None:
    """Extract task number from branches like task-12 or feature/task/12."""
    match = TASK_BRANCH_RE.search(branch or "")
    if not match:
        return None
    return int(match.group(1))


Handler = Callable[[Any, CIEvent], dict[str, Any]]


def handle_ci_event(
    session: Any, event: CIEvent, *, api: Any | None = None
) -> dict[str, Any]:
    """Upsert run, triage failures, enforce flake budget, block linked tasks."""
    from cerebro.github import triage as triage_mod
    from cerebro.github.runs import upsert_from_github

    org_id = settings.github_default_org_id
    row = upsert_from_github(
        session,
        org_id=org_id,
        owner=event.owner,
        repo=event.repo,
        payload=event.raw_run,
    )
    triage_mod.link_task_for_run(session, row, head_branch=event.head_branch)
    result: dict[str, Any] = {
        "handled": True,
        "run_id": event.run_id,
        "ci_run_id": row.id,
        "task_id": row.task_id,
    }

    if event.status == "completed" and event.conclusion == "failure":
        client = api
        if client is None:
            try:
                from cerebro.github.api import GitHubAPI
                from cerebro.github.app_auth import GitHubAppAuth

                client = GitHubAPI(GitHubAppAuth())
            except Exception:  # noqa: BLE001 - webhook stays up without creds
                client = None
        flake = triage_mod.handle_failed_run(
            session, event=event, ci_run=row, api=client
        )
        result["flake"] = flake
        blocked = triage_mod.block_task_on_red_build(session, ci_run=row, event=event)
        result["blocked_task"] = blocked

    session.commit()
    return result


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, Any]:
    """FastAPI route: verify signature, normalize workflow_run, triage."""
    body = await request.body()
    try:
        verify_signature(body, x_hub_signature_256, settings.github_webhook_secret)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if x_github_event and x_github_event != "workflow_run":
        return {"handled": False, "reason": "ignored_event", "event": x_github_event}

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc

    event = normalize_workflow_run(payload)
    if event is None:
        return {"handled": False, "reason": "not_workflow_run"}

    session = SessionLocal()
    try:
        return handle_ci_event(session, event)
    finally:
        session.close()
