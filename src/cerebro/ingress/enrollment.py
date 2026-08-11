import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from cerebro.db.models import ChannelBinding, Org, Population, Principal


def _ensure_org(session: Session, org_id: str) -> None:
    """Create the org row if it doesn't exist yet (first-touch, not a seed script)."""
    if session.get(Org, org_id) is None:
        session.add(Org(id=org_id, name=org_id, created_at=datetime.now(UTC)))
        session.flush()


def enroll_unknown_sender(
    session: Session, org_id: str, channel: str, channel_id: str, conversation_id: str
) -> tuple[Principal, ChannelBinding]:
    """Enroll an unknown sender by creating a principal and binding.

    Returns (principal, binding) tuple.
    """
    _ensure_org(session, org_id)

    principal_id = str(uuid.uuid4())
    principal = Principal(
        id=principal_id,
        org_id=org_id,
        population=Population.CLIENT,
        created_at=datetime.now(UTC),
    )
    session.add(principal)
    session.flush()

    # verified="verified" (not "pending"): no promotion step exists yet to move a
    # pending binding to verified, so pending was a dead end - resolve_principal
    # never re-matched it and every later message re-enrolled the same sender.
    binding = ChannelBinding(
        id=str(uuid.uuid4()),
        principal_id=principal_id,
        channel=channel,
        channel_id=channel_id,
        conversation_id=conversation_id,
        verified="verified",
        created_at=datetime.now(UTC),
    )
    session.add(binding)
    session.commit()

    return principal, binding
