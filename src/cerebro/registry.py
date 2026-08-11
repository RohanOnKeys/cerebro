"""Tool registry with population-gated tool access."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Population, Principal
from cerebro.github import api as github_api
from cerebro.github import app_auth as github_auth
from cerebro.github import runs as ci_runs_service
from cerebro.ingress.enrollment import enroll_unknown_sender
from cerebro.membrane import crossings as crossings_service
from cerebro.membrane import policy as policy_service
from cerebro.membrane import redact as redact_service
from cerebro.services import meetings as meetings_service
from cerebro.services import orders as orders_service
from cerebro.services import summaries as summaries_service
from cerebro.services import tasks as tasks_service

# Internal populations that may run team/ops tools. CLIENT is excluded.
_TEAM_POPULATIONS = frozenset(
    {
        Population.OPS,
        Population.DEV,
        Population.LEAD,
        Population.ADMIN,
    }
)
_ALL_POPULATIONS = frozenset(Population)


@dataclass(frozen=True)
class ToolSpec:
    """Specification for a registered tool.

    Attributes:
        name: Stable tool identifier.
        description: Human-readable summary for callers/LLMs.
        parameters: JSON-Schema-like parameter object.
        handler: Callable that executes the tool.
        allowed_populations: Populations permitted to see/invoke this tool.
        tier: 1 runs immediately; >=2 requires CONFIRM before execution.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    allowed_populations: frozenset[Population]
    tier: int = 1


def whoami(*, principal: Principal, **_: Any) -> dict[str, str]:
    """Return the caller's principal identity."""
    return {
        "principal_id": principal.id,
        "org_id": principal.org_id,
        "population": principal.population.value,
        "email": principal.email or "",
    }


def enroll_principal(
    *,
    session: Session,
    org_id: str,
    channel: str,
    channel_id: str,
    conversation_id: str,
    **_: Any,
) -> dict[str, str]:
    """Enroll an unknown sender via the existing enrollment service.

    Creates a CLIENT principal and pending channel binding. Restricted to
    team/ops populations in the registry (not CLIENT self-service).
    """
    principal, binding = enroll_unknown_sender(
        session, org_id, channel, channel_id, conversation_id
    )
    return {
        "principal_id": principal.id,
        "binding_id": binding.id,
        "population": principal.population.value,
        "verified": binding.verified,
    }


def set_availability(
    *,
    principal: Principal,
    available: bool,
    note: str = "",
    **_: Any,
) -> dict[str, Any]:
    """Record availability for the calling principal.

    Thin Phase 2.1 handler: persists no ledger yet; returns a structured ack
    so cortex can call a real tool later without inventing a parallel identity
    system.
    """
    return {
        "principal_id": principal.id,
        "available": available,
        "note": note,
        "status": "recorded",
    }


def open_order(
    *,
    session: Session,
    principal: Principal,
    text: str = "",
    order_type: str | None = None,
    fields: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Open an orders ledger row from free text and/or explicit type."""
    order = orders_service.open_order(
        session,
        principal=principal,
        text=text,
        order_type=order_type,
        fields=fields,
    )
    return orders_service.serialize_order(order)


def update_order_fields(
    *,
    session: Session,
    principal: Principal,
    order_id: str,
    fields: dict[str, Any],
    **_: Any,
) -> dict[str, Any]:
    """Merge fields into an existing order."""
    order = orders_service.update_order_fields(
        session,
        order_id=order_id,
        fields=fields,
        principal=principal,
    )
    if order is None:
        return {"error": "order_not_found", "order_id": order_id}
    return orders_service.serialize_order(order)


def order_status(
    *,
    session: Session,
    order_id: str,
    **_: Any,
) -> dict[str, Any]:
    """Return status for one order."""
    result = orders_service.order_status(session, order_id=order_id)
    if result is None:
        return {"error": "order_not_found", "order_id": order_id}
    return result


def list_orders(
    *,
    session: Session,
    principal: Principal,
    status: str | None = None,
    limit: int = 20,
    **_: Any,
) -> dict[str, Any]:
    """List orders visible to the calling principal."""
    items = orders_service.list_orders(
        session,
        principal=principal,
        status=status,
        limit=limit,
    )
    return {"orders": items, "count": len(items)}



def decompose_order(
    *,
    session: Session,
    order_id: str,
    designation: str,
    required_skills: list[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Split an order into one or more tasks, unassigned."""
    from cerebro.db.models import Order

    order = session.query(Order).filter(Order.id == order_id).first()
    if order is None:
        return {"error": "order_not_found", "order_id": order_id}
    created = tasks_service.decompose_order(
        session, order, designation=designation, required_skills=required_skills
    )
    return {
        "tasks": [tasks_service.serialize_task(task) for task in created],
        "count": len(created),
    }


def assign_task(
    *,
    session: Session,
    org_id: str,
    number: int,
    **_: Any,
) -> dict[str, Any]:
    """Assign an open task via the designation/skills/wip_cap/load chain, then fan it out."""
    task = tasks_service.get_task_by_number(session, org_id=org_id, number=number)
    if task is None:
        return {"error": "task_not_found", "number": number}
    assignee = tasks_service.assign_task(session, task)
    if assignee is None:
        return {"error": "no_eligible_assignee", "number": number}
    tasks_service.send_task_card(session, task)
    return {
        "task": tasks_service.serialize_task(task),
        "assignee_principal_id": assignee.id,
    }


def ack_task(
    *,
    session: Session,
    principal: Principal,
    number: int,
    **_: Any,
) -> dict[str, Any]:
    """Acknowledge a task, cancelling its remaining ladder rungs."""
    task = tasks_service.ack_task(session, org_id=principal.org_id, number=number)
    if task is None:
        return {"error": "task_not_found", "number": number}
    return tasks_service.serialize_task(task)


def block_task(
    *,
    session: Session,
    principal: Principal,
    number: int,
    reason: str = "",
    **_: Any,
) -> dict[str, Any]:
    """Mark a task blocked and notify the org's leads."""
    task = tasks_service.block_task(
        session, org_id=principal.org_id, number=number, principal=principal, reason=reason
    )
    if task is None:
        return {"error": "task_not_found", "number": number}
    return tasks_service.serialize_task(task)


def list_tasks(
    *,
    session: Session,
    principal: Principal,
    **_: Any,
) -> dict[str, Any]:
    """List tasks assigned to the calling principal."""
    items = tasks_service.list_tasks_for_principal(session, principal=principal)
    return {
        "tasks": [tasks_service.serialize_task(task) for task in items],
        "count": len(items),
    }



def schedule_meeting(
    *,
    session: Session,
    principal: Principal,
    title: str,
    attendee_principal_ids: list[str] | None = None,
    duration_minutes: int = 30,
    starts_at: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Schedule a meeting, finding the earliest free slot when starts_at is omitted."""
    import datetime as _dt

    if starts_at:
        parsed_starts_at = _dt.datetime.fromisoformat(starts_at)
    else:
        parsed_starts_at = meetings_service.find_slot(
            [], duration_minutes=duration_minutes, after=_dt.datetime.now(_dt.UTC)
        )
    meeting = meetings_service.schedule_meeting(
        session,
        org_id=principal.org_id,
        organizer_principal_id=principal.id,
        title=title,
        starts_at=parsed_starts_at,
        duration_minutes=duration_minutes,
        attendee_principal_ids=attendee_principal_ids or [],
    )
    return meetings_service.serialize_meeting(meeting)


def rsvp_meeting(
    *,
    session: Session,
    principal: Principal,
    meeting_id: str,
    status: str,
    **_: Any,
) -> dict[str, Any]:
    """Record the calling principal's RSVP for a meeting."""
    attendee = meetings_service.rsvp(
        session, meeting_id=meeting_id, principal_id=principal.id, status=status
    )
    if attendee is None:
        return {"error": "attendee_not_found", "meeting_id": meeting_id}
    return {
        "meeting_id": meeting_id,
        "principal_id": principal.id,
        "rsvp_status": attendee.rsvp_status,
    }


def list_meetings(
    *,
    session: Session,
    principal: Principal,
    **_: Any,
) -> dict[str, Any]:
    """List meetings the calling principal organizes or attends."""
    items = meetings_service.list_meetings(session, principal_id=principal.id)
    return {
        "meetings": [meetings_service.serialize_meeting(meeting) for meeting in items],
        "count": len(items),
    }


def meeting_status(
    *,
    session: Session,
    meeting_id: str,
    **_: Any,
) -> dict[str, Any]:
    """Check one meeting's details and every attendee's RSVP status."""
    result = meetings_service.meeting_status(session, meeting_id=meeting_id)
    if result is None:
        return {"error": "meeting_not_found", "meeting_id": meeting_id}
    return result


def request_summary(
    *,
    session: Session,
    principal: Principal,
    topic: str,
    **_: Any,
) -> dict[str, Any]:
    """Open a summary request and notify the requester."""
    order = summaries_service.request_summary(session, principal=principal, topic=topic)
    return orders_service.serialize_order(order)


def submit_summary(
    *,
    session: Session,
    principal: Principal,
    order_id: str,
    text: str,
    **_: Any,
) -> dict[str, Any]:
    """Submit one participant's dump toward a summary order."""
    entry = summaries_service.submit_summary_entry(
        session, order_id=order_id, principal_id=principal.id, text=text
    )
    return {"id": entry.id, "order_id": entry.order_id, "principal_id": entry.principal_id}



def relay_to_population(
    *,
    session: Session,
    principal: Principal,
    target_population: str,
    text: str = "",
    order_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Relay content across a population boundary under membrane policy.

    Records the crossing before resolving any content (audit-first), denies
    fail-closed if no policy row covers (caller's population, target), and
    redacts digest text per the matched rule before marking the crossing sent.
    """
    from cerebro.db.models import Order

    decision = policy_service.evaluate_crossing(
        session, source=principal.population, target=target_population
    )
    crossing = crossings_service.record_crossing(
        session,
        org_id=principal.org_id,
        principal_id=principal.id,
        source=principal.population,
        target=target_population,
        action=decision.action,
        content_ref=order_id,
    )

    if decision.action == "deny":
        return {
            "error": "relay_denied",
            "target_population": target_population,
            "crossing_id": crossing.id,
        }

    content = text
    if order_id:
        order = session.query(Order).filter(Order.id == order_id).first()
        if order is None:
            return {"error": "order_not_found", "order_id": order_id}
        fields = orders_service.loads_fields(order.fields_json)
        content = fields.get("digest", order.free_text or "")

    if decision.action == "redact":
        content = redact_service.redact_digest_text(content, decision.redact_fields)

    crossings_service.mark_crossing_sent(session, crossing.id)
    return {
        "delivered_to": target_population,
        "action": decision.action,
        "content": content,
        "crossing_id": crossing.id,
    }


def _github_api_from_settings() -> github_api.GitHubAPI:
    """Build a GitHubAPI using app credentials from settings."""
    auth = github_auth.GitHubAppAuth()
    return github_api.GitHubAPI(auth)


def list_ci_runs(
    *,
    session: Session,
    principal: Principal,
    owner: str,
    repo: str,
    branch: str = "",
    status: str = "",
    per_page: int = 30,
    api: github_api.GitHubAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """List recent GitHub Actions runs and upsert them into the CI ledger."""
    client = api or _github_api_from_settings()
    try:
        rows = ci_runs_service.list_ci_runs_live(
            session,
            client,
            org_id=principal.org_id,
            owner=owner,
            repo=repo,
            branch=branch or None,
            status=status or None,
            per_page=per_page,
        )
    except (github_auth.GitHubAuthError, github_api.GitHubAPIError) as exc:
        return {"error": "github_error", "detail": str(exc)}
    return {
        "runs": [ci_runs_service.serialize_ci_run(row) for row in rows],
        "count": len(rows),
    }


def explain_ci_failure(
    *,
    session: Session,
    principal: Principal,
    owner: str,
    repo: str,
    run_id: str,
    api: github_api.GitHubAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Explain a failed CI run using jobs, steps, and check annotations."""
    client = api or _github_api_from_settings()
    try:
        return ci_runs_service.explain_ci_failure(
            session,
            client,
            org_id=principal.org_id,
            owner=owner,
            repo=repo,
            run_id=run_id,
        )
    except (github_auth.GitHubAuthError, github_api.GitHubAPIError) as exc:
        return {"error": "github_error", "detail": str(exc)}


def rerun_workflow(
    *,
    session: Session,
    principal: Principal,
    owner: str,
    repo: str,
    run_id: str,
    api: github_api.GitHubAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Re-run a workflow run (tier-2; gated by verify executor)."""
    client = api or _github_api_from_settings()
    try:
        client.rerun_workflow(owner, repo, run_id)
    except (github_auth.GitHubAuthError, github_api.GitHubAPIError) as exc:
        return {"error": "github_error", "detail": str(exc)}
    return {"status": "rerun_requested", "owner": owner, "repo": repo, "run_id": run_id}


def dispatch_workflow(
    *,
    session: Session,
    principal: Principal,
    owner: str,
    repo: str,
    workflow_id: str,
    ref: str,
    inputs: dict[str, Any] | None = None,
    api: github_api.GitHubAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Dispatch a workflow (tier-2; gated by verify executor)."""
    client = api or _github_api_from_settings()
    try:
        client.dispatch_workflow(
            owner, repo, workflow_id, ref=ref, inputs=inputs or None
        )
    except (github_auth.GitHubAuthError, github_api.GitHubAPIError) as exc:
        return {"error": "github_error", "detail": str(exc)}
    return {
        "status": "dispatched",
        "owner": owner,
        "repo": repo,
        "workflow_id": workflow_id,
        "ref": ref,
        "requested_by": principal.id,
    }


def cancel_run(
    *,
    session: Session,
    principal: Principal,
    owner: str,
    repo: str,
    run_id: str,
    api: github_api.GitHubAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Cancel an in-progress workflow run (tier-2; gated by verify executor)."""
    client = api or _github_api_from_settings()
    try:
        client.cancel_run(owner, repo, run_id)
    except (github_auth.GitHubAuthError, github_api.GitHubAPIError) as exc:
        return {"error": "github_error", "detail": str(exc)}
    return {"status": "cancel_requested", "owner": owner, "repo": repo, "run_id": run_id}


TOOLS: dict[str, ToolSpec] = {
    "whoami": ToolSpec(
        name="whoami",
        description="Return the caller's principal id, org, and population.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=whoami,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "enroll_principal": ToolSpec(
        name="enroll_principal",
        description="Enroll an unknown sender as a CLIENT principal with a pending binding.",
        parameters={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "channel": {"type": "string"},
                "channel_id": {"type": "string"},
                "conversation_id": {"type": "string"},
            },
            "required": ["org_id", "channel", "channel_id", "conversation_id"],
            "additionalProperties": False,
        },
        handler=enroll_principal,
        # Ops/team only: CLIENT must not enroll other principals.
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "set_availability": ToolSpec(
        name="set_availability",
        description="Record whether the calling principal is currently available.",
        parameters={
            "type": "object",
            "properties": {
                "available": {"type": "boolean"},
                "note": {"type": "string"},
            },
            "required": ["available"],
            "additionalProperties": False,
        },
        handler=set_availability,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "open_order": ToolSpec(
        name="open_order",
        description="Open an order from free text; sets order_type on the ledger row.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "order_type": {"type": "string"},
                "fields": {"type": "object"},
            },
            "additionalProperties": False,
        },
        handler=open_order,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "update_order_fields": ToolSpec(
        name="update_order_fields",
        description="Update collected fields on an existing order.",
        parameters={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["order_id", "fields"],
            "additionalProperties": False,
        },
        handler=update_order_fields,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "order_status": ToolSpec(
        name="order_status",
        description="Fetch one order by id.",
        parameters={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
        handler=order_status,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "list_orders": ToolSpec(
        name="list_orders",
        description="List orders for the caller's organization.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=list_orders,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "decompose_order": ToolSpec(
        name="decompose_order",
        description="Split an order into one or more unassigned tasks.",
        parameters={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "designation": {"type": "string"},
                "required_skills": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["order_id", "designation"],
            "additionalProperties": False,
        },
        handler=decompose_order,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "assign_task": ToolSpec(
        name="assign_task",
        description=(
            "Assign an open task by designation, skills, wip_cap, then lowest load; "
            "fans out the task card on success."
        ),
        parameters={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "number": {"type": "integer"},
            },
            "required": ["org_id", "number"],
            "additionalProperties": False,
        },
        handler=assign_task,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "ack_task": ToolSpec(
        name="ack_task",
        description="Acknowledge an assigned task by its number.",
        parameters={
            "type": "object",
            "properties": {"number": {"type": "integer"}},
            "required": ["number"],
            "additionalProperties": False,
        },
        handler=ack_task,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "block_task": ToolSpec(
        name="block_task",
        description="Mark an assigned task blocked and notify the org's leads.",
        parameters={
            "type": "object",
            "properties": {
                "number": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["number"],
            "additionalProperties": False,
        },
        handler=block_task,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "list_tasks": ToolSpec(
        name="list_tasks",
        description="List tasks assigned to the calling principal.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=list_tasks,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "schedule_meeting": ToolSpec(
        name="schedule_meeting",
        description=(
            "Schedule a meeting with attendees; finds the earliest free slot when "
            "starts_at is omitted."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "attendee_principal_ids": {"type": "array", "items": {"type": "string"}},
                "duration_minutes": {"type": "integer"},
                "starts_at": {"type": "string"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=schedule_meeting,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "rsvp_meeting": ToolSpec(
        name="rsvp_meeting",
        description="Record the caller's RSVP (yes/no) for a meeting.",
        parameters={
            "type": "object",
            "properties": {
                "meeting_id": {"type": "string"},
                "status": {"type": "string", "enum": ["yes", "no", "pending"]},
            },
            "required": ["meeting_id", "status"],
            "additionalProperties": False,
        },
        handler=rsvp_meeting,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "list_meetings": ToolSpec(
        name="list_meetings",
        description="List meetings the caller organizes or attends.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=list_meetings,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "meeting_status": ToolSpec(
        name="meeting_status",
        description="Check one meeting's details and every attendee's RSVP status.",
        parameters={
            "type": "object",
            "properties": {"meeting_id": {"type": "string"}},
            "required": ["meeting_id"],
            "additionalProperties": False,
        },
        handler=meeting_status,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "request_summary": ToolSpec(
        name="request_summary",
        description="Open a summary request for a topic and notify the requester.",
        parameters={
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
            "additionalProperties": False,
        },
        handler=request_summary,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "submit_summary": ToolSpec(
        name="submit_summary",
        description="Submit your notes/dump toward an open summary order.",
        parameters={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["order_id", "text"],
            "additionalProperties": False,
        },
        handler=submit_summary,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "relay_to_population": ToolSpec(
        name="relay_to_population",
        description=(
            "Relay text or an order's digest to another population, applying membrane "
            "policy (allow/redact/deny) for the caller's population -> target pair."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target_population": {"type": "string"},
                "text": {"type": "string"},
                "order_id": {"type": "string"},
            },
            "required": ["target_population"],
            "additionalProperties": False,
        },
        handler=relay_to_population,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "list_ci_runs": ToolSpec(
        name="list_ci_runs",
        description="List recent GitHub Actions workflow runs for a repository.",
        parameters={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "branch": {"type": "string"},
                "status": {"type": "string"},
                "per_page": {"type": "integer"},
            },
            "required": ["owner", "repo"],
            "additionalProperties": False,
        },
        handler=list_ci_runs,
        allowed_populations=_TEAM_POPULATIONS,
        tier=1,
    ),
    "explain_ci_failure": ToolSpec(
        name="explain_ci_failure",
        description="Explain why a GitHub Actions run failed (jobs, steps, annotations).",
        parameters={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["owner", "repo", "run_id"],
            "additionalProperties": False,
        },
        handler=explain_ci_failure,
        allowed_populations=_TEAM_POPULATIONS,
        tier=1,
    ),
    "rerun_workflow": ToolSpec(
        name="rerun_workflow",
        description="Re-run a GitHub Actions workflow run (requires CONFIRM).",
        parameters={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["owner", "repo", "run_id"],
            "additionalProperties": False,
        },
        handler=rerun_workflow,
        allowed_populations=_TEAM_POPULATIONS,
        tier=2,
    ),
    "dispatch_workflow": ToolSpec(
        name="dispatch_workflow",
        description="Dispatch a GitHub Actions workflow (requires CONFIRM).",
        parameters={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "workflow_id": {"type": "string"},
                "ref": {"type": "string"},
                "inputs": {"type": "object"},
            },
            "required": ["owner", "repo", "workflow_id", "ref"],
            "additionalProperties": False,
        },
        handler=dispatch_workflow,
        allowed_populations=_TEAM_POPULATIONS,
        tier=2,
    ),
    "cancel_run": ToolSpec(
        name="cancel_run",
        description="Cancel an in-progress GitHub Actions run (requires CONFIRM).",
        parameters={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["owner", "repo", "run_id"],
            "additionalProperties": False,
        },
        handler=cancel_run,
        allowed_populations=_TEAM_POPULATIONS,
        tier=2,
    ),
}


def _build_tools_for() -> dict[Population, tuple[ToolSpec, ...]]:
    """Build the population → allowed tools index."""
    return {
        population: tuple(
            tool for tool in TOOLS.values() if population in tool.allowed_populations
        )
        for population in Population
    }


TOOLS_FOR: Mapping[Population, tuple[ToolSpec, ...]] = _build_tools_for()


def tools_for(population: Population) -> tuple[ToolSpec, ...]:
    """Return tools allowed for the given population."""
    return TOOLS_FOR[population]
