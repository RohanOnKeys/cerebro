"""Gap chase job: due asks, backoff, abandon + escalate."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import (
    FieldSpec,
    GapChase,
    GapChaseStatus,
    Order,
    OrderStatus,
)
from cerebro.services import nudges as nudges_service
from cerebro.services.gap_harvester import (
    MAX_ASKS,
    ChaseView,
    FieldSpecView,
    missing_fields,
    record_ask,
    should_ask,
)
from cerebro.services.orders import loads_fields

DEFAULT_SPECS: dict[str, tuple[FieldSpecView, ...]] = {
    "schedule": (
        FieldSpecView("when", required=True, validator="date"),
        FieldSpecView("attendees", required=True, validator="nonempty"),
    ),
    "notify": (FieldSpecView("message", required=True, validator="nonempty"),),
    "general": (FieldSpecView("email", required=True, validator="email"),),
    "ci": (FieldSpecView("workflow", required=True, validator="nonempty"),),
    "summary": (FieldSpecView("topic", required=True, validator="nonempty"),),
}


def specs_for_order(session: Session, order: Order) -> list[FieldSpecView]:
    """Load field specs for an order type (DB first, else defaults)."""
    rows = (
        session.query(FieldSpec)
        .filter(FieldSpec.order_type == order.order_type)
        .all()
    )
    if rows:
        return [
            FieldSpecView(
                field_name=row.field_name,
                required=bool(row.required),
                validator=row.validator or "nonempty",
            )
            for row in rows
        ]
    return list(DEFAULT_SPECS.get(order.order_type, DEFAULT_SPECS["general"]))


def _to_chase_view(chase: GapChase) -> ChaseView:
    return ChaseView(
        field_name=chase.field_name,
        ask_count=chase.ask_count or 0,
        last_asked_at=chase.last_asked_at,
        next_ask_at=chase.next_ask_at,
        status=chase.status,
    )


def _apply_chase_view(chase: GapChase, view: ChaseView) -> None:
    chase.ask_count = view.ask_count
    chase.last_asked_at = view.last_asked_at
    chase.next_ask_at = view.next_ask_at
    chase.status = view.status


def ensure_gap_chases(session: Session, order: Order) -> list[GapChase]:
    """Create open chases for currently missing required fields."""
    specs = specs_for_order(session, order)
    fields = loads_fields(order.fields_json)
    needed = missing_fields(fields, specs)
    existing = {
        chase.field_name: chase
        for chase in session.query(GapChase).filter(GapChase.order_id == order.id).all()
    }
    created: list[GapChase] = []
    now = datetime.now(UTC)
    for field_name in needed:
        current = existing.get(field_name)
        if current is not None and current.status == GapChaseStatus.OPEN.value:
            continue
        if current is not None and current.status == GapChaseStatus.CLOSED.value:
            continue
        if current is not None and current.status == GapChaseStatus.EXHAUSTED.value:
            continue
        chase = GapChase(
            id=str(uuid.uuid4()),
            order_id=order.id,
            field_name=field_name,
            status=GapChaseStatus.OPEN.value,
            ask_count=0,
            last_asked_at=None,
            next_ask_at=now,
            created_at=now,
        )
        session.add(chase)
        created.append(chase)
    if created:
        session.commit()
    return created


def process_due_gap_chases(
    session: Session,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Run one gap-chase tick: ask once, respect backoff, escalate on 4th."""
    moment = now or datetime.now(UTC)
    actions: list[dict[str, Any]] = []
    open_orders = (
        session.query(Order)
        .filter(Order.status.in_([OrderStatus.OPEN.value, OrderStatus.IN_PROGRESS.value]))
        .all()
    )
    for order in open_orders:
        ensure_gap_chases(session, order)
        chases = (
            session.query(GapChase)
            .filter(
                GapChase.order_id == order.id,
                GapChase.status == GapChaseStatus.OPEN.value,
            )
            .all()
        )
        for chase in chases:
            view = _to_chase_view(chase)
            if not should_ask(view, now=moment):
                continue

            if view.ask_count >= MAX_ASKS - 1:
                updated = record_ask(view, asked_at=moment)
                _apply_chase_view(chase, updated)
                session.commit()
                nudge = nudges_service.create_gap_escalate_nudge(
                    session,
                    org_id=order.org_id,
                    principal_id=order.principal_id,
                    order_id=order.id,
                    gap_chase_id=chase.id,
                    field_name=chase.field_name,
                )
                actions.append(
                    {
                        "action": "escalate",
                        "order_id": order.id,
                        "field_name": chase.field_name,
                        "ask_count": chase.ask_count,
                        "nudge_id": nudge.id,
                        "chase_status": chase.status,
                    }
                )
                continue

            updated = record_ask(view, asked_at=moment)
            _apply_chase_view(chase, updated)
            session.commit()
            nudge = nudges_service.create_gap_ask_nudge(
                session,
                org_id=order.org_id,
                principal_id=order.principal_id,
                order_id=order.id,
                gap_chase_id=chase.id,
                field_name=chase.field_name,
            )
            actions.append(
                {
                    "action": "ask",
                    "order_id": order.id,
                    "field_name": chase.field_name,
                    "ask_count": chase.ask_count,
                    "nudge_id": nudge.id,
                    "body": nudge.body,
                    "chase_status": chase.status,
                }
            )

    session.commit()
    return actions


def register_gap_chase_job(scheduler: Any, session_factory: Any, *, interval_seconds: float = 5.0) -> str:
    """Attach the gap chase job to a Scheduler on a daemon thread."""

    def _tick() -> None:
        session = session_factory()
        try:
            process_due_gap_chases(session)
        finally:
            session.close()

    return scheduler.every(interval_seconds, _tick, name="gap_chase")
