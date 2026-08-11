"""Crossing audit ledger: recorded before a relay is attempted, not after."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Crossing, CrossingStatus, Population


def _population_value(population: Population | str) -> str:
    return population.value if hasattr(population, "value") else population


def record_crossing(
    session: Session,
    *,
    org_id: str,
    principal_id: str,
    source: Population | str,
    target: Population | str,
    action: str,
    content_ref: str | None = None,
) -> Crossing:
    """Persist the intent to cross a boundary before any content is sent."""
    status = CrossingStatus.DENIED.value if action == "deny" else CrossingStatus.RECORDED.value
    crossing = Crossing(
        id=str(uuid.uuid4()),
        org_id=org_id,
        principal_id=principal_id,
        source_population=_population_value(source),
        target_population=_population_value(target),
        action=action,
        content_ref=content_ref,
        status=status,
        created_at=datetime.now(UTC),
        sent_at=None,
    )
    session.add(crossing)
    session.commit()
    return crossing


def mark_crossing_sent(session: Session, crossing_id: str) -> Crossing | None:
    """Mark a recorded crossing as actually delivered."""
    crossing = session.query(Crossing).filter(Crossing.id == crossing_id).first()
    if crossing is None:
        return None
    if crossing.status == CrossingStatus.DENIED.value:
        return crossing
    crossing.status = CrossingStatus.SENT.value
    crossing.sent_at = datetime.now(UTC)
    session.commit()
    return crossing


def list_crossings(session: Session, *, org_id: str) -> list[Crossing]:
    """List crossing audit rows for an org, newest first."""
    return (
        session.query(Crossing)
        .filter(Crossing.org_id == org_id)
        .order_by(Crossing.created_at.desc())
        .all()
    )


def serialize_crossing(crossing: Crossing) -> dict[str, Any]:
    """Serialize a Crossing row for tool/API responses."""
    return {
        "id": crossing.id,
        "org_id": crossing.org_id,
        "principal_id": crossing.principal_id,
        "source_population": crossing.source_population,
        "target_population": crossing.target_population,
        "action": crossing.action,
        "content_ref": crossing.content_ref,
        "status": crossing.status,
        "created_at": crossing.created_at.isoformat() if crossing.created_at else "",
        "sent_at": crossing.sent_at.isoformat() if crossing.sent_at else "",
    }
