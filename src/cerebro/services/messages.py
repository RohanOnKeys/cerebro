"""Message ledger: persisted per-principal conversation memory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Message, Principal

HISTORY_WINDOW = 12


def record_message(
    session: Session,
    *,
    principal: Principal,
    channel: str,
    role: str,
    content: str,
) -> Message:
    """Persist one turn, embedding the principal id and their population (type)."""
    message = Message(
        id=str(uuid.uuid4()),
        org_id=principal.org_id,
        principal_id=principal.id,
        channel=channel,
        population=principal.population.value
        if hasattr(principal.population, "value")
        else principal.population,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )
    session.add(message)
    session.commit()
    return message


def recent_messages(
    session: Session, *, principal_id: str, limit: int = HISTORY_WINDOW
) -> list[Message]:
    """Return the last `limit` messages for a principal, oldest first."""
    rows = (
        session.query(Message)
        .filter(Message.principal_id == principal_id)
        .order_by(Message.created_at.desc())
        .limit(max(1, limit))
        .all()
    )
    return list(reversed(rows))


def to_chat_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert ledger rows into the role/content dicts run_tool_loop expects."""
    return [{"role": message.role, "content": message.content} for message in messages]
