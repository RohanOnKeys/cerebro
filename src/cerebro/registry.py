"""Tool registry with population-gated tool access."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from cerebro.config import settings
from cerebro.db.models import NudgeKind, Population, Principal
from cerebro.gcal import api as gcal_api
from cerebro.gcal import auth as gcal_auth
from cerebro.github import api as github_api
from cerebro.github import app_auth as github_auth
from cerebro.github import runs as ci_runs_service
from cerebro.ingress.enrollment import enroll_unknown_sender
from cerebro.jira import api as jira_api
from cerebro.jira import auth as jira_auth
from cerebro.membrane import crossings as crossings_service
from cerebro.membrane import policy as policy_service
from cerebro.membrane import redact as redact_service
from cerebro.services import meetings as meetings_service
from cerebro.services import nudges as nudges_service
from cerebro.services import orders as orders_service
from cerebro.services import summaries as summaries_service
from cerebro.services import tasks as tasks_service
from cerebro.zoom import api as zoom_api
from cerebro.zoom import auth as zoom_auth

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
    principal: Principal,
    channel: str,
    channel_id: str,
    conversation_id: str,
    org_id: str | None = None,
    **_: Any,
) -> dict[str, str]:
    """Enroll a different, not-yet-known sender via the existing enrollment service.

    Creates a CLIENT principal and pending channel binding. Restricted to
    team/ops populations in the registry (not CLIENT self-service). org_id
    defaults to the calling principal's own org - a team member enrolling a
    new external contact is virtually always adding them to their own team,
    not an arbitrary other org by raw id, so there's no reason to ask for it.
    """
    target_org_id = org_id or principal.org_id
    new_principal, binding = enroll_unknown_sender(
        session, target_org_id, channel, channel_id, conversation_id
    )
    return {
        "principal_id": new_principal.id,
        "binding_id": binding.id,
        "population": new_principal.population.value,
        "verified": binding.verified,
    }


def create_team(
    *,
    session: Session,
    principal: Principal,
    name: str,
    code: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Create a new team (org) and return its join code.

    The caller hands that code out on Slack, Discord, or email (any
    channel's onboarding flow accepts it - see ingress/enrollment.py) to
    invite clients or teammates into the new team. This is a CREATE, not a
    join: a caller-supplied `code` that's already taken is rejected rather
    than silently reusing that other team, unlike the implicit
    resolve-or-create an unrecognized code triggers during onboarding.
    """
    from cerebro.services import orgs as orgs_service

    chosen_code = code or orgs_service.generate_join_code()
    org, created = orgs_service.resolve_or_create_org_by_code(session, chosen_code)
    if not created:
        return {
            "error": "code_already_in_use",
            "code": orgs_service.normalize_code(chosen_code),
        }
    org.name = name
    session.commit()
    return {"org_id": org.id, "name": org.name, "join_code": org.join_code}


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



def _gcal_api_from_settings() -> gcal_api.GoogleCalendarAPI:
    """Build a GoogleCalendarAPI using the shared service-account credentials."""
    auth = gcal_auth.GoogleCalendarAuth()
    return gcal_api.GoogleCalendarAPI(auth)


def _zoom_api_from_settings() -> zoom_api.ZoomAPI:
    """Build a ZoomAPI using the shared Server-to-Server credentials."""
    auth = zoom_auth.ZoomAuth()
    return zoom_api.ZoomAPI(auth)


def _attendee_emails(session: Session, principal_ids: list[str]) -> list[str]:
    """Resolve principal ids to their emails, dropping any without one."""
    if not principal_ids:
        return []
    rows = (
        session.query(Principal.email)
        .filter(Principal.id.in_(principal_ids), Principal.email.isnot(None))
        .all()
    )
    return [email for (email,) in rows if email]


def schedule_meeting(
    *,
    session: Session,
    principal: Principal,
    title: str,
    attendee_principal_ids: list[str] | None = None,
    duration_minutes: int = 30,
    starts_at: str | None = None,
    provider: str = "none",
    gcal_client: gcal_api.GoogleCalendarAPI | None = None,
    zoom_client: zoom_api.ZoomAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Schedule a meeting, finding the earliest free slot when starts_at is omitted.

    provider="meet"/"zoom" also creates a real conferencing link and, only
    for "meet", checks real availability via Google's free/busy instead of
    the historical busy=[] (Zoom has no calendar concept to query, and
    "none" never had one). The external call happens before the internal
    row is written, so a failed external call never leaves a dead-link
    meeting behind.
    """
    import datetime as _dt

    attendee_ids = attendee_principal_ids or []

    if starts_at:
        parsed_starts_at = _dt.datetime.fromisoformat(starts_at)
    elif provider == "meet":
        client = gcal_client or _gcal_api_from_settings()
        window_start = _dt.datetime.now(_dt.UTC)
        try:
            busy = client.free_busy(
                settings.gcal_calendar_id,
                _attendee_emails(session, [principal.id, *attendee_ids]),
                time_min=window_start,
                time_max=window_start + _dt.timedelta(days=7),
            )
        except (gcal_auth.GoogleCalendarAuthError, gcal_api.GoogleCalendarAPIError) as exc:
            return {"error": "gcal_error", "detail": str(exc)}
        parsed_starts_at = meetings_service.find_slot(
            busy, duration_minutes=duration_minutes, after=window_start
        )
    else:
        parsed_starts_at = meetings_service.find_slot(
            [], duration_minutes=duration_minutes, after=_dt.datetime.now(_dt.UTC)
        )

    join_url: str | None = None
    external_event_id: str | None = None
    if provider == "meet":
        client = gcal_client or _gcal_api_from_settings()
        ends_at = parsed_starts_at + _dt.timedelta(minutes=duration_minutes)
        try:
            event = client.create_event(
                settings.gcal_calendar_id,
                summary=title,
                start=parsed_starts_at,
                end=ends_at,
                attendee_emails=_attendee_emails(session, attendee_ids),
            )
        except (gcal_auth.GoogleCalendarAuthError, gcal_api.GoogleCalendarAPIError) as exc:
            return {"error": "gcal_error", "detail": str(exc)}
        join_url = event["meet_link"]
        external_event_id = str(event["event_id"]) if event["event_id"] else None
    elif provider == "zoom":
        if not settings.zoom_user_id:
            return {"error": "missing_zoom_user_id"}
        client = zoom_client or _zoom_api_from_settings()
        try:
            zoom_meeting = client.create_meeting(
                settings.zoom_user_id,
                topic=title,
                start_time=parsed_starts_at,
                duration_minutes=duration_minutes,
            )
        except (zoom_auth.ZoomAuthError, zoom_api.ZoomAPIError) as exc:
            return {"error": "zoom_error", "detail": str(exc)}
        join_url = zoom_meeting["join_url"]
        external_event_id = (
            str(zoom_meeting["meeting_id"]) if zoom_meeting["meeting_id"] else None
        )

    meeting = meetings_service.schedule_meeting(
        session,
        org_id=principal.org_id,
        organizer_principal_id=principal.id,
        title=title,
        starts_at=parsed_starts_at,
        duration_minutes=duration_minutes,
        attendee_principal_ids=attendee_ids,
        provider=provider if provider != "none" else "",
        join_url=join_url,
        external_event_id=external_event_id,
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


def cancel_meeting(
    *,
    session: Session,
    principal: Principal,
    meeting_id: str,
    gcal_client: gcal_api.GoogleCalendarAPI | None = None,
    zoom_client: zoom_api.ZoomAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Cancel a meeting the caller organizes; notifies every attendee.

    For a real provider, the external event/meeting is cancelled first; on
    failure the internal row is left untouched (retryable) rather than
    cancelling internally and orphaning the real Meet/Zoom booking.
    """
    from cerebro.db.models import Meeting

    meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()
    if meeting is None:
        return {"error": "meeting_not_found", "meeting_id": meeting_id}
    if meeting.organizer_principal_id != principal.id:
        return {"error": "not_organizer", "meeting_id": meeting_id}

    if meeting.provider == "meet" and meeting.external_event_id:
        client = gcal_client or _gcal_api_from_settings()
        try:
            client.delete_event(settings.gcal_calendar_id, meeting.external_event_id)
        except (gcal_auth.GoogleCalendarAuthError, gcal_api.GoogleCalendarAPIError) as exc:
            return {"error": "gcal_error", "detail": str(exc)}
    elif meeting.provider == "zoom" and meeting.external_event_id:
        client = zoom_client or _zoom_api_from_settings()
        try:
            client.delete_meeting(meeting.external_event_id)
        except (zoom_auth.ZoomAuthError, zoom_api.ZoomAPIError) as exc:
            return {"error": "zoom_error", "detail": str(exc)}

    cancelled = meetings_service.cancel_meeting(session, meeting=meeting)
    return meetings_service.serialize_meeting(cancelled)


def _resolve_due_at(due_at: str | None, in_seconds: int | None) -> Any:
    """Prefer in_seconds when given: it's computed here, server-side, from
    the real clock at the moment the tool actually executes - immune to
    both model arithmetic mistakes and the latency between when the model
    read "current time" in its prompt and when the tool call lands, which
    is exactly what produced a wrong offset live (asked for 30s, landed on
    8s) even with the correct current-time context already in the prompt.
    Falls back to the model-computed absolute due_at for anything that's
    actually an absolute date/time rather than a short relative offset.
    """
    import datetime as _dt

    if in_seconds is not None:
        if in_seconds <= 0:
            raise ValueError("in_seconds must be positive")
        return _dt.datetime.now(_dt.UTC) + _dt.timedelta(seconds=in_seconds)
    if due_at:
        return _dt.datetime.fromisoformat(due_at)
    raise ValueError("either due_at or in_seconds is required")


def request_deadline(
    *,
    session: Session,
    principal: Principal,
    order_id: str,
    due_at: str | None = None,
    in_seconds: int | None = None,
    note: str = "",
    **_: Any,
) -> dict[str, Any]:
    """A client (or team member) flags a deadline the team should hit for
    an order. Open to every population, including CLIENT - this and
    whatever data-followup reminders gap_chase already generates are the
    only reminder-system surface a client gets; set_reminder/list_reminders/
    cancel_reminder/calendar_view are team-only.

    Targets the order's current task assignee, or every org lead if
    unassigned - same fallback route_client_feedback/block_task use for
    unassigned-escalation, not a membrane crossing (this is a scheduling
    fact about the order, not client content being relayed to a
    population).
    """
    from cerebro.db.models import Order, ReminderKind
    from cerebro.services import reminders as reminders_service

    order = (
        session.query(Order)
        .filter(Order.id == order_id, Order.org_id == principal.org_id)
        .first()
    )
    if order is None:
        return {"error": "order_not_found", "order_id": order_id}

    try:
        parsed_due_at = _resolve_due_at(due_at, in_seconds)
    except ValueError as exc:
        return {"error": "invalid_due_at_or_in_seconds", "detail": str(exc)}
    due_at_iso = parsed_due_at.isoformat()

    targets = reminders_service.resolve_deadline_targets(
        session, org_id=principal.org_id, order_id=order_id
    )
    if not targets:
        return {"error": "no_eligible_recipient", "order_id": order_id}

    subject = f"Deadline for order {order_id}"
    created = []
    for target in targets:
        reminder = reminders_service.create_reminder(
            session,
            org_id=principal.org_id,
            created_by_principal_id=principal.id,
            principal_id=target.id,
            subject=subject,
            due_at=parsed_due_at,
            kind=ReminderKind.DEADLINE,
            note=note,
            order_id=order_id,
        )
        nudges_service.create_nudge(
            session,
            org_id=principal.org_id,
            principal_id=target.id,
            order_id=order_id,
            body=f"Deadline requested for order {order_id}: {due_at_iso}" + (f" ({note})" if note else ""),
            kind=NudgeKind.DEADLINE_REQUESTED.value,
        )
        created.append(reminders_service.serialize_reminder(reminder))

    return {"order_id": order_id, "due_at": due_at_iso, "reminders": created}


def set_reminder(
    *,
    session: Session,
    principal: Principal,
    subject: str,
    due_at: str | None = None,
    in_seconds: int | None = None,
    note: str = "",
    for_principal_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """General-purpose reminder, defaults to reminding the caller. Team-only:
    a CLIENT can request a deadline (request_deadline) but not set arbitrary
    reminders for themselves or anyone else."""
    from cerebro.db.models import ReminderKind
    from cerebro.services import reminders as reminders_service

    target_id = for_principal_id or principal.id
    if target_id != principal.id:
        target = session.query(Principal).filter(Principal.id == target_id).first()
        if target is None or target.org_id != principal.org_id:
            return {"error": "principal_not_found", "principal_id": target_id}

    try:
        parsed_due_at = _resolve_due_at(due_at, in_seconds)
    except ValueError as exc:
        return {"error": "invalid_due_at_or_in_seconds", "detail": str(exc)}

    reminder = reminders_service.create_reminder(
        session,
        org_id=principal.org_id,
        created_by_principal_id=principal.id,
        principal_id=target_id,
        subject=subject,
        due_at=parsed_due_at,
        kind=ReminderKind.GENERAL,
        note=note,
    )
    return reminders_service.serialize_reminder(reminder)


def list_reminders(
    *,
    session: Session,
    principal: Principal,
    mine_only: bool = True,
    **_: Any,
) -> dict[str, Any]:
    """List pending reminders/deadlines, soonest due first. Team-only."""
    from cerebro.services import reminders as reminders_service

    rows = reminders_service.list_reminders(
        session,
        org_id=principal.org_id,
        principal_id=principal.id if mine_only else None,
    )
    return {"items": [reminders_service.serialize_reminder(r) for r in rows]}


def cancel_reminder(
    *,
    session: Session,
    principal: Principal,
    reminder_id: str,
    **_: Any,
) -> dict[str, Any]:
    """Cancel a pending reminder/deadline. Team-only."""
    from cerebro.services import reminders as reminders_service

    cancelled = reminders_service.cancel_reminder(
        session, org_id=principal.org_id, reminder_id=reminder_id
    )
    if cancelled is None:
        return {"error": "reminder_not_found_or_not_pending", "reminder_id": reminder_id}
    return reminders_service.serialize_reminder(cancelled)


def calendar_view(
    *,
    session: Session,
    principal: Principal,
    days_ahead: int = 7,
    **_: Any,
) -> dict[str, Any]:
    """Merged view of the caller's upcoming meetings and reminders/deadlines
    over the next `days_ahead` days - the "self-hosted calendar" read side.
    Team-only."""
    import datetime as _dt

    from cerebro.services import reminders as reminders_service

    now = _dt.datetime.now(_dt.UTC)
    horizon = now + _dt.timedelta(days=days_ahead)

    meetings = [
        meetings_service.serialize_meeting(m)
        for m in meetings_service.list_meetings(session, principal_id=principal.id)
        if m.starts_at <= horizon.replace(tzinfo=None)
    ]
    reminders = [
        reminders_service.serialize_reminder(r)
        for r in reminders_service.list_reminders(
            session, org_id=principal.org_id, principal_id=principal.id
        )
        if r.due_at <= horizon.replace(tzinfo=None)
    ]
    return {"meetings": meetings, "reminders": reminders, "days_ahead": days_ahead}


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


def route_client_feedback(
    *,
    session: Session,
    principal: Principal,
    text: str,
    task_number: int | None = None,
    order_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Route client feedback to the task's assignee, or the org's leads if unassigned.

    Delivery to an assignee (always dev/ops in practice) goes through the same
    audited membrane crossing as relay_to_population. The lead fallback skips
    that crossing and notifies directly instead, the same way block_task
    already notifies leads: that path is unassigned-escalation between team
    members, not content crossing out to a client, so there is nothing for
    the membrane to gate (and no client->lead policy row is seeded for it).
    """
    from cerebro.db.models import Task

    task: Task | None = None
    if task_number is not None:
        task = tasks_service.get_task_by_number(
            session, org_id=principal.org_id, number=task_number
        )
        if task is None:
            return {"error": "task_not_found", "number": task_number}
    elif order_id is not None:
        task = (
            session.query(Task)
            .filter(Task.org_id == principal.org_id, Task.order_id == order_id)
            .order_by(Task.created_at.desc())
            .first()
        )

    assignee = None
    if task is not None and task.assignee_principal_id:
        assignee = (
            session.query(Principal).filter(Principal.id == task.assignee_principal_id).first()
        )

    label = f"task {task.number}" if task else "your account"

    if assignee is not None:
        decision = policy_service.evaluate_crossing(
            session, source=principal.population, target=assignee.population
        )
        crossing = crossings_service.record_crossing(
            session,
            org_id=principal.org_id,
            principal_id=principal.id,
            source=principal.population,
            target=assignee.population,
            action=decision.action,
            content_ref=task.id if task else None,
        )
        if decision.action == "deny":
            return {
                "error": "feedback_denied",
                "principal_id": assignee.id,
                "crossing_id": crossing.id,
            }
        content = text
        if decision.action == "redact":
            content = redact_service.redact_digest_text(content, decision.redact_fields)
        nudges_service.create_nudge(
            session,
            org_id=principal.org_id,
            principal_id=assignee.id,
            order_id=task.order_id if task else order_id,
            body=f"Client feedback on {label}: {content}",
            kind=NudgeKind.CLIENT_FEEDBACK.value,
        )
        crossings_service.mark_crossing_sent(session, crossing.id)
        return {
            "task_number": task.number if task else None,
            "routed_to": assignee.id,
            "action": decision.action,
            "crossing_id": crossing.id,
        }

    leads = (
        session.query(Principal)
        .filter(Principal.org_id == principal.org_id, Principal.population == Population.LEAD)
        .all()
    )
    if not leads:
        return {"error": "no_recipient_found"}
    for lead in leads:
        nudges_service.create_nudge(
            session,
            org_id=principal.org_id,
            principal_id=lead.id,
            order_id=task.order_id if task else order_id,
            body=f"Client feedback on {label} (unassigned): {text}",
            kind=NudgeKind.CLIENT_FEEDBACK.value,
        )
    return {
        "task_number": task.number if task else None,
        "routed_to": [lead.id for lead in leads],
        "action": "escalated_to_leads",
    }


def post_incident_update(
    *,
    session: Session,
    principal: Principal,
    summary: str,
    target_population: str = "lead",
    severity: str = "info",
    **_: Any,
) -> dict[str, Any]:
    """Broadcast an incident/status update to every principal in a team population.

    Internal team-to-team, so this bypasses the membrane crossing system the
    same way block_task's lead notification does, it is not content crossing
    out to a client.
    """
    recipients = (
        session.query(Principal)
        .filter(
            Principal.org_id == principal.org_id,
            Principal.population == target_population,
        )
        .all()
    )
    if not recipients:
        return {"error": "no_recipients", "target_population": target_population}

    body = f"[{severity.upper()}] {principal.id}: {summary}"
    nudge_ids = []
    for recipient in recipients:
        nudge = nudges_service.create_nudge(
            session,
            org_id=principal.org_id,
            principal_id=recipient.id,
            body=body,
            kind=NudgeKind.INCIDENT_UPDATE.value,
        )
        nudge_ids.append(nudge.id)

    return {
        "target_population": target_population,
        "notified": [recipient.id for recipient in recipients],
        "nudge_ids": nudge_ids,
        "severity": severity,
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


def _jira_api_from_settings() -> jira_api.JiraAPI:
    """Build a JiraAPI using the shared API-token credentials from settings."""
    auth = jira_auth.JiraAuth()
    return jira_api.JiraAPI(auth)


def create_jira_ticket(
    *,
    session: Session,
    principal: Principal,
    summary: str,
    description: str = "",
    project_key: str = "",
    issue_type: str = "Task",
    labels: list[str] | None = None,
    api: jira_api.JiraAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Create a Jira ticket, falling back to the org's default project key."""
    key = project_key or settings.jira_default_project_key
    if not key:
        return {"error": "missing_project_key"}
    client = api or _jira_api_from_settings()
    try:
        issue = client.create_issue(
            key,
            summary=summary,
            description=description,
            issue_type=issue_type,
            labels=labels,
        )
    except (jira_auth.JiraAuthError, jira_api.JiraAPIError) as exc:
        return {"error": "jira_error", "detail": str(exc)}
    issue_key = str(issue.get("key") or "")
    return {
        "issue_key": issue_key,
        "issue_url": f"{client.auth.base_url}/browse/{issue_key}",
        "id": issue.get("id"),
        "created_by": principal.id,
    }


def jira_issue_status(
    *,
    session: Session,
    principal: Principal,
    issue_key: str,
    api: jira_api.JiraAPI | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Fetch a Jira issue's current status/summary."""
    client = api or _jira_api_from_settings()
    try:
        issue = client.get_issue(issue_key)
    except (jira_auth.JiraAuthError, jira_api.JiraAPIError) as exc:
        return {"error": "jira_error", "detail": str(exc)}
    fields = issue.get("fields") or {}
    status = (fields.get("status") or {}).get("name", "")
    return {
        "issue_key": issue_key,
        "summary": fields.get("summary", ""),
        "status": status,
    }


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
        description=(
            "Enroll a DIFFERENT, not-yet-known sender (identified by a raw channel "
            "id you already have from elsewhere - a Telegram/Discord/Slack id or "
            "email address) as a CLIENT with a verified binding. This is NOT for "
            "the principal currently talking to you to change their own type or "
            "re-enroll themselves - there is no self-service tool for that. If "
            "the caller asks to be enrolled/re-enrolled/switched to a different "
            "population, refuse and explain the limit instead of asking them for "
            "their own org_id, channel, channel_id, or conversation_id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": (
                        "Optional - defaults to the calling principal's own org. "
                        "Only pass this to enroll someone into a different org."
                    ),
                },
                "channel": {"type": "string"},
                "channel_id": {"type": "string"},
                "conversation_id": {"type": "string"},
            },
            "required": ["channel", "channel_id", "conversation_id"],
            "additionalProperties": False,
        },
        handler=enroll_principal,
        # Ops/team only: CLIENT must not enroll other principals.
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "create_team": ToolSpec(
        name="create_team",
        description=(
            "Create a new team (org) and return its join code, to hand out on "
            "Slack, Discord, or email so clients or teammates can be onboarded "
            "into it. Rejects an explicit code that's already in use."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "code": {
                    "type": "string",
                    "description": "Optional; auto-generated if omitted.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=create_team,
        # Ops/team only: a CLIENT shouldn't be able to spin up new teams.
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
            "starts_at is omitted. provider=meet/zoom also creates a real "
            "conferencing link (meet additionally checks real availability)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "attendee_principal_ids": {"type": "array", "items": {"type": "string"}},
                "duration_minutes": {"type": "integer"},
                "starts_at": {"type": "string"},
                "provider": {"type": "string", "enum": ["none", "meet", "zoom"]},
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
    "cancel_meeting": ToolSpec(
        name="cancel_meeting",
        description="Cancel a meeting you organize and notify every attendee.",
        parameters={
            "type": "object",
            "properties": {"meeting_id": {"type": "string"}},
            "required": ["meeting_id"],
            "additionalProperties": False,
        },
        handler=cancel_meeting,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "request_deadline": ToolSpec(
        name="request_deadline",
        description=(
            "Flag a deadline the team should hit for an order. Targets the "
            "order's assignee, or every org lead if unassigned. Give either "
            "in_seconds or due_at, not both."
        ),
        parameters={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "in_seconds": {
                    "type": "integer",
                    "description": (
                        "Preferred for a short relative offset ('in 30 seconds', "
                        "'in 10 minutes' -> 600). Computed from the real clock at "
                        "the moment the tool runs, so it can't drift the way your "
                        "own arithmetic plus response latency can."
                    ),
                },
                "due_at": {
                    "type": "string",
                    "description": (
                        "ISO 8601 timestamp, for an actual absolute date/time "
                        "('tomorrow at 3pm', 'next Friday') rather than a short "
                        "relative offset - use in_seconds for those instead. "
                        "Compute this from the current time given in your system "
                        "context - do not ask the user for it."
                    ),
                },
                "note": {"type": "string"},
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
        handler=request_deadline,
        # The one reminder-system tool CLIENT gets, alongside the automatic
        # data-followup reminders gap_chase already sends.
        allowed_populations=_ALL_POPULATIONS,
    ),
    "set_reminder": ToolSpec(
        name="set_reminder",
        description=(
            "Set a general-purpose reminder for yourself or a teammate. Give "
            "either in_seconds or due_at, not both."
        ),
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "in_seconds": {
                    "type": "integer",
                    "description": (
                        "Preferred for a short relative offset ('in 30 seconds', "
                        "'in 10 minutes' -> 600). Computed from the real clock at "
                        "the moment the tool runs, so it can't drift the way your "
                        "own arithmetic plus response latency can."
                    ),
                },
                "due_at": {
                    "type": "string",
                    "description": (
                        "ISO 8601 timestamp, for an actual absolute date/time "
                        "('tomorrow at 3pm', 'next Friday') rather than a short "
                        "relative offset - use in_seconds for those instead. "
                        "Compute this from the current time given in your system "
                        "context - do not ask the user for it."
                    ),
                },
                "note": {"type": "string"},
                "for_principal_id": {
                    "type": "string",
                    "description": "Defaults to the caller if omitted.",
                },
            },
            "required": ["subject"],
            "additionalProperties": False,
        },
        handler=set_reminder,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "list_reminders": ToolSpec(
        name="list_reminders",
        description="List pending reminders/deadlines, soonest due first.",
        parameters={
            "type": "object",
            "properties": {
                "mine_only": {"type": "boolean", "description": "Default true."},
            },
            "additionalProperties": False,
        },
        handler=list_reminders,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "cancel_reminder": ToolSpec(
        name="cancel_reminder",
        description="Cancel a pending reminder or deadline.",
        parameters={
            "type": "object",
            "properties": {"reminder_id": {"type": "string"}},
            "required": ["reminder_id"],
            "additionalProperties": False,
        },
        handler=cancel_reminder,
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "calendar_view": ToolSpec(
        name="calendar_view",
        description=(
            "Self-hosted calendar: merged view of your upcoming meetings "
            "and reminders/deadlines over the next N days."
        ),
        parameters={
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "Default 7."},
            },
            "additionalProperties": False,
        },
        handler=calendar_view,
        allowed_populations=_TEAM_POPULATIONS,
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
    "route_client_feedback": ToolSpec(
        name="route_client_feedback",
        description=(
            "Route client feedback to the person actually in charge: the assignee of "
            "the given task (or the order's most recent task), falling back to the "
            "org's leads if nothing is assigned yet."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "task_number": {"type": "integer"},
                "order_id": {"type": "string"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=route_client_feedback,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "post_incident_update": ToolSpec(
        name="post_incident_update",
        description=(
            "Broadcast an incident or status update to every principal in a team "
            "population (e.g. tell ops the staging db is down)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "target_population": {
                    "type": "string",
                    "enum": ["dev", "ops", "lead", "admin"],
                },
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
        handler=post_incident_update,
        allowed_populations=_TEAM_POPULATIONS,
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
    "create_jira_ticket": ToolSpec(
        name="create_jira_ticket",
        description=(
            "Create a Jira ticket. Falls back to the org's default project key "
            "when project_key is omitted."
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "project_key": {"type": "string"},
                "issue_type": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
        handler=create_jira_ticket,
        allowed_populations=_TEAM_POPULATIONS,
        tier=1,
    ),
    "jira_issue_status": ToolSpec(
        name="jira_issue_status",
        description="Fetch a Jira issue's current status and summary.",
        parameters={
            "type": "object",
            "properties": {"issue_key": {"type": "string"}},
            "required": ["issue_key"],
            "additionalProperties": False,
        },
        handler=jira_issue_status,
        allowed_populations=_TEAM_POPULATIONS,
        tier=1,
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
