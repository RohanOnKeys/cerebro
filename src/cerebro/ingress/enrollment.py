import uuid
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from cerebro.db.models import Principal, Org, ChannelBinding, Population


def enroll_unknown_sender(
    session: Session, org_id: str, channel: str, channel_id: str, conversation_id: str
) -> tuple[Principal, ChannelBinding]:
    """Enroll an unknown sender by creating a principal and binding.

    Returns (principal, binding) tuple.
    """
    principal_id = str(uuid.uuid4())
    principal = Principal(
        id=principal_id,
        org_id=org_id,
        population=Population.CLIENT,
        created_at=datetime.now(UTC),
    )
    session.add(principal)
    session.flush()

    binding = ChannelBinding(
        id=str(uuid.uuid4()),
        principal_id=principal_id,
        channel=channel,
        channel_id=channel_id,
        conversation_id=conversation_id,
        verified="pending",
        created_at=datetime.now(UTC),
    )
    session.add(binding)
    session.commit()

    return principal, binding
