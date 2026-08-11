"""Summaries: request, chase, merge (2 submissions or T+24h), action items -> tasks."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.config import settings
from cerebro.db.models import NudgeKind, Order, OrderStatus, Principal, SummaryEntry
from cerebro.services import nudges as nudges_service
from cerebro.services import tasks as tasks_service
from cerebro.services.orders import dumps_fields, loads_fields, open_order

_ACTION_ITEM_RE = re.compile(r"^(?:[-*]\s+|(?:action|todo)\s*:\s*)(.+)$", re.I)

MERGE_DEADLINE_MINUTES = 24 * 60
MERGE_ENTRY_COUNT = 2


def _as_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC-aware (SQLite often returns naive values)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _scaled_deadline_minutes() -> float:
    return MERGE_DEADLINE_MINUTES * settings.nudge_time_scale


def extract_action_items(text: str) -> list[str]:
    """Pure: pull bullet/TODO/action lines out of free text."""
    items = []
    for line in (text or "").splitlines():
        match = _ACTION_ITEM_RE.match(line.strip())
        if match:
            items.append(match.group(1).strip())
    return items


def request_summary(session: Session, *, principal: Principal, topic: str) -> Order:
    """Open a summary-type order and notify the requester."""
    order = open_order(
        session,
        principal=principal,
        text=topic,
        order_type="summary",
        fields={"topic": topic},
    )
    nudges_service.create_nudge(
        session,
        org_id=order.org_id,
        principal_id=principal.id,
        order_id=order.id,
        body=f"Summary requested: {topic}. Please submit your notes.",
        kind=NudgeKind.SUMMARY_REQUEST.value,
    )
    return order


def submit_summary_entry(
    session: Session, *, order_id: str, principal_id: str, text: str
) -> SummaryEntry:
    """Record one participant's dump for a summary order."""
    entry = SummaryEntry(
        id=str(uuid.uuid4()),
        order_id=order_id,
        principal_id=principal_id,
        text=text,
        submitted_at=datetime.now(UTC),
    )
    session.add(entry)
    session.commit()
    return entry


def list_summary_entries(session: Session, order_id: str) -> list[SummaryEntry]:
    """List submitted entries for a summary order, oldest first."""
    return (
        session.query(SummaryEntry)
        .filter(SummaryEntry.order_id == order_id)
        .order_by(SummaryEntry.submitted_at.asc())
        .all()
    )


def merge_summary(
    session: Session,
    order: Order,
    entries: list[SummaryEntry],
    *,
    now: datetime | None = None,
    designation: str = "dev",
) -> dict[str, Any]:
    """Merge entries into one digest, complete the order, spawn tasks from action items."""
    moment = now or datetime.now(UTC)
    digest = (
        "\n\n".join(f"{entry.principal_id}: {entry.text}" for entry in entries)
        if entries
        else "(no submissions received)"
    )
    fields = loads_fields(order.fields_json)
    fields["digest"] = digest
    order.fields_json = dumps_fields(fields)
    order.status = OrderStatus.COMPLETE.value
    order.updated_at = moment

    action_items: list[str] = []
    for entry in entries:
        action_items.extend(extract_action_items(entry.text))

    created_tasks = [
        tasks_service.create_task(
            session,
            org_id=order.org_id,
            order_id=order.id,
            title=item,
            designation=designation,
        )
        for item in action_items
    ]
    session.commit()
    return {
        "action": "merge",
        "order_id": order.id,
        "digest": digest,
        "entry_count": len(entries),
        "task_ids": [task.id for task in created_tasks],
    }


def process_due_summary_chases(
    session: Session, *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Nudge the requester once if no submissions have arrived by the half-deadline."""
    moment = now or datetime.now(UTC)
    actions: list[dict[str, Any]] = []
    orders = (
        session.query(Order)
        .filter(Order.order_type == "summary", Order.status != OrderStatus.COMPLETE.value)
        .all()
    )
    for order in orders:
        fields = loads_fields(order.fields_json)
        if fields.get("chased"):
            continue
        entry_count = (
            session.query(SummaryEntry).filter(SummaryEntry.order_id == order.id).count()
        )
        if entry_count > 0:
            continue
        elapsed_minutes = (moment - _as_utc(order.created_at)).total_seconds() / 60
        if elapsed_minutes < _scaled_deadline_minutes() / 2:
            continue
        nudge = nudges_service.create_nudge(
            session,
            org_id=order.org_id,
            principal_id=order.principal_id,
            order_id=order.id,
            body=f"Still waiting on your summary for '{fields.get('topic', '')}'.",
            kind=NudgeKind.SUMMARY_CHASE.value,
        )
        fields["chased"] = True
        order.fields_json = dumps_fields(fields)
        actions.append({"action": "chase", "order_id": order.id, "nudge_id": nudge.id})
    session.commit()
    return actions


def process_due_summary_merges(
    session: Session, *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Merge any summary order with 2+ submissions or past its (scaled) T+24h deadline."""
    moment = now or datetime.now(UTC)
    actions: list[dict[str, Any]] = []
    orders = (
        session.query(Order)
        .filter(Order.order_type == "summary", Order.status != OrderStatus.COMPLETE.value)
        .all()
    )
    for order in orders:
        entries = list_summary_entries(session, order.id)
        elapsed_minutes = (moment - _as_utc(order.created_at)).total_seconds() / 60
        should_merge = (
            len(entries) >= MERGE_ENTRY_COUNT or elapsed_minutes >= _scaled_deadline_minutes()
        )
        if not should_merge:
            continue
        actions.append(merge_summary(session, order, entries, now=moment))
    return actions


def register_summary_jobs(
    scheduler: Any, session_factory: Any, *, interval_seconds: float = 5.0
) -> tuple[str, str]:
    """Attach the summary chase and merge jobs to a Scheduler on a daemon thread."""

    def _chase_tick() -> None:
        session = session_factory()
        try:
            process_due_summary_chases(session)
        finally:
            session.close()

    def _merge_tick() -> None:
        session = session_factory()
        try:
            process_due_summary_merges(session)
        finally:
            session.close()

    chase_name = scheduler.every(interval_seconds, _chase_tick, name="summary_chase")
    merge_name = scheduler.every(interval_seconds, _merge_tick, name="summary_merge")
    return chase_name, merge_name
