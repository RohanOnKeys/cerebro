from sqlalchemy.orm import Session
from cerebro.db.models import Principal, ChannelBinding


def resolve_principal(session: Session, channel: str, channel_id: str) -> Principal | None:
    """Resolve a sender to a principal by (channel, channel_id) binding.

    Returns the Principal if found and verified, None otherwise.
    """
    binding = session.query(ChannelBinding).filter(
        ChannelBinding.channel == channel,
        ChannelBinding.channel_id == channel_id,
        ChannelBinding.verified == "verified",
    ).first()

    if not binding:
        return None

    return session.query(Principal).filter(Principal.id == binding.principal_id).first()


def touch_binding(
    session: Session, principal_id: str, channel: str, channel_id: str
) -> ChannelBinding:
    """Create or update a channel binding for a principal.

    Returns the binding (created or existing).
    """
    binding = session.query(ChannelBinding).filter(
        ChannelBinding.principal_id == principal_id,
        ChannelBinding.channel == channel,
        ChannelBinding.channel_id == channel_id,
    ).first()

    if binding:
        return binding

    from datetime import datetime
    import uuid

    binding = ChannelBinding(
        id=str(uuid.uuid4()),
        principal_id=principal_id,
        channel=channel,
        channel_id=channel_id,
        verified="pending",
        created_at=datetime.utcnow(),
    )
    session.add(binding)
    session.commit()
    return binding
