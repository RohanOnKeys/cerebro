"""Nudge ledger helpers for gap chase follow-ups and escalations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Nudge, NudgeKind, NudgeStatus


def create_nudge(
    session: Session,
    *,
    org_id: str,
    principal_id: str,
    body: str,
    kind: str,
    order_id: str | None = None,
    gap_chase_id: str | None = None,
    status: str = NudgeStatus.PENDING.value,
) -> Nudge:
    """Persist a nudge row."""
    nudge = Nudge(
        id=str(uuid.uuid4()),
        org_id=org_id,
        principal_id=principal_id,
        order_id=order_id,
        gap_chase_id=gap_chase_id,
        kind=kind,
        body=body,
        status=status,
        created_at=datetime.now(UTC),
        sent_at=None,
    )
    session.add(nudge)
    session.commit()
    return nudge


def create_gap_ask_nudge(
    session: Session,
    *,
    org_id: str,
    principal_id: str,
    order_id: str,
    gap_chase_id: str,
    field_name: str,
) -> Nudge:
    """Create a follow-up question nudge for a missing field."""
    body = f"Quick follow-up: what is the {field_name} for order {order_id}?"
    return create_nudge(
        session,
        org_id=org_id,
        principal_id=principal_id,
        order_id=order_id,
        gap_chase_id=gap_chase_id,
        kind=NudgeKind.GAP_ASK.value,
        body=body,
    )


def create_gap_escalate_nudge(
    session: Session,
    *,
    org_id: str,
    principal_id: str,
    order_id: str,
    gap_chase_id: str,
    field_name: str,
) -> Nudge:
    """Create an escalation nudge after chase abandonment."""
    body = (
        f"Escalation: order {order_id} abandoned waiting for {field_name}. "
        "Please intervene."
    )
    return create_nudge(
        session,
        org_id=org_id,
        principal_id=principal_id,
        order_id=order_id,
        gap_chase_id=gap_chase_id,
        kind=NudgeKind.GAP_ESCALATE.value,
        body=body,
    )


def mark_nudge_sent(session: Session, nudge_id: str) -> Nudge | None:
    """Mark a nudge as sent."""
    nudge = session.query(Nudge).filter(Nudge.id == nudge_id).first()
    if nudge is None:
        return None
    nudge.status = NudgeStatus.SENT.value
    nudge.sent_at = datetime.now(UTC)
    session.commit()
    return nudge


def list_nudges(
    session: Session,
    *,
    order_id: str | None = None,
    kind: str | None = None,
    status: str | None = None,
) -> list[Nudge]:
    """List nudges with optional filters."""
    query = session.query(Nudge)
    if order_id is not None:
        query = query.filter(Nudge.order_id == order_id)
    if kind is not None:
        query = query.filter(Nudge.kind == kind)
    if status is not None:
        query = query.filter(Nudge.status == status)
    return query.order_by(Nudge.created_at.asc()).all()


def serialize_nudge(nudge: Nudge) -> dict[str, Any]:
    """Serialize a nudge for tests/API responses."""
    return {
        "id": nudge.id,
        "org_id": nudge.org_id,
        "principal_id": nudge.principal_id,
        "order_id": nudge.order_id,
        "gap_chase_id": nudge.gap_chase_id,
        "kind": nudge.kind,
        "body": nudge.body,
        "status": nudge.status,
        "created_at": nudge.created_at.isoformat() if nudge.created_at else "",
        "sent_at": nudge.sent_at.isoformat() if nudge.sent_at else "",
    }
