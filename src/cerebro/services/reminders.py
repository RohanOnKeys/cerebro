"""Self-hosted reminder/deadline system: create, fire, list, cancel.

No external calendar dependency (unlike the GCal/Zoom meeting providers in
gcal/zoom) - this is a plain DB-backed row plus a clock tick, same shape as
the existing meeting-reminder and task-ladder jobs. `kind` distinguishes a
general team reminder from a client-requested deadline; both fire the same
way, one-shot, when `due_at` passes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import (
    NudgeKind,
    Principal,
    Reminder,
    ReminderKind,
    ReminderStatus,
    Task,
)
from cerebro.services import nudges as nudges_service


def _as_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC-aware (SQLite/Postgres round trips often
    come back naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def serialize_reminder(reminder: Reminder) -> dict[str, Any]:
    return {
        "id": reminder.id,
        "org_id": reminder.org_id,
        "created_by_principal_id": reminder.created_by_principal_id,
        "principal_id": reminder.principal_id,
        "order_id": reminder.order_id,
        "kind": reminder.kind,
        "subject": reminder.subject,
        "note": reminder.note,
        "due_at": reminder.due_at.isoformat() if reminder.due_at else "",
        "status": reminder.status,
        "created_at": reminder.created_at.isoformat() if reminder.created_at else "",
        "fired_at": reminder.fired_at.isoformat() if reminder.fired_at else None,
    }


def create_reminder(
    session: Session,
    *,
    org_id: str,
    created_by_principal_id: str,
    principal_id: str,
    subject: str,
    due_at: datetime,
    kind: ReminderKind = ReminderKind.GENERAL,
    note: str = "",
    order_id: str | None = None,
) -> Reminder:
    """Persist a pending reminder. Does not itself send anything - a
    DEADLINE also gets an immediate nudge (see request_deadline_targets
    for the resolution logic callers use before calling this); a due-time
    nudge always comes later from process_due_reminders."""
    reminder = Reminder(
        id=str(uuid.uuid4()),
        org_id=org_id,
        created_by_principal_id=created_by_principal_id,
        principal_id=principal_id,
        order_id=order_id,
        kind=kind.value,
        subject=subject,
        note=note,
        due_at=due_at,
        status=ReminderStatus.PENDING.value,
        created_at=datetime.now(UTC),
    )
    session.add(reminder)
    session.commit()
    return reminder


def resolve_deadline_targets(session: Session, *, org_id: str, order_id: str) -> list[Principal]:
    """Who a client's deadline request should target: the order's current
    task assignee, or every org lead if unassigned/no task exists yet -
    same unassigned-escalation fallback as block_task/route_client_feedback."""
    task = (
        session.query(Task)
        .filter(Task.org_id == org_id, Task.order_id == order_id)
        .order_by(Task.created_at.desc())
        .first()
    )
    if task is not None and task.assignee_principal_id:
        assignee = (
            session.query(Principal)
            .filter(Principal.id == task.assignee_principal_id)
            .first()
        )
        if assignee is not None:
            return [assignee]

    return (
        session.query(Principal)
        .filter(Principal.org_id == org_id, Principal.population == "lead")
        .all()
    )


def list_reminders(
    session: Session,
    *,
    org_id: str,
    principal_id: str | None = None,
    status: str = ReminderStatus.PENDING.value,
) -> list[Reminder]:
    """List reminders, soonest due first. principal_id=None returns every
    reminder in the org (team-wide visibility - never used for CLIENT)."""
    query = session.query(Reminder).filter(Reminder.org_id == org_id)
    if principal_id is not None:
        query = query.filter(Reminder.principal_id == principal_id)
    if status is not None:
        query = query.filter(Reminder.status == status)
    return query.order_by(Reminder.due_at.asc()).all()


def cancel_reminder(session: Session, *, org_id: str, reminder_id: str) -> Reminder | None:
    reminder = (
        session.query(Reminder)
        .filter(Reminder.id == reminder_id, Reminder.org_id == org_id)
        .first()
    )
    if reminder is None or reminder.status != ReminderStatus.PENDING.value:
        return None
    reminder.status = ReminderStatus.CANCELLED.value
    session.commit()
    return reminder


def process_due_reminders(session: Session, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Clock tick: fire every pending reminder whose due_at has passed.
    One-shot, no backoff/escalation ladder (unlike gap_chase/task_ladder) -
    a missed deadline still needs a human to notice and re-chase it, the
    same way an unanswered meeting reminder does today."""
    moment = now or datetime.now(UTC)
    fired: list[dict[str, Any]] = []

    due = (
        session.query(Reminder)
        .filter(
            Reminder.status == ReminderStatus.PENDING.value,
            Reminder.due_at <= moment,
        )
        .all()
    )
    for reminder in due:
        if _as_utc(reminder.due_at) > moment:
            continue
        label = "Deadline" if reminder.kind == ReminderKind.DEADLINE.value else "Reminder"
        nudge = nudges_service.create_nudge(
            session,
            org_id=reminder.org_id,
            principal_id=reminder.principal_id,
            order_id=reminder.order_id,
            body=f"{label} due now: {reminder.subject}" + (f" ({reminder.note})" if reminder.note else ""),
            kind=NudgeKind.REMINDER_DUE.value,
        )
        reminder.status = ReminderStatus.FIRED.value
        reminder.fired_at = moment
        fired.append(
            {
                "reminder_id": reminder.id,
                "principal_id": reminder.principal_id,
                "kind": reminder.kind,
                "nudge_id": nudge.id,
            }
        )
    session.commit()
    return fired


def register_reminder_job(
    scheduler: Any, session_factory: Any, *, interval_seconds: float = 5.0
) -> str:
    """Attach the reminder-firing job to a Scheduler on a daemon thread."""

    def _tick() -> None:
        session = session_factory()
        try:
            process_due_reminders(session)
        finally:
            session.close()

    return scheduler.every(interval_seconds, _tick, name="reminders")
