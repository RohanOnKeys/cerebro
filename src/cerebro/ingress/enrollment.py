import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from cerebro.db.models import ChannelBinding, Org, PendingEnrollment, Population, Principal

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TEAM_ROLE_ALIASES: dict[str, Population] = {
    "OPS": Population.OPS,
    "DEV": Population.DEV,
    "LEAD": Population.LEAD,
    "ADMIN": Population.ADMIN,
}
ENROLLMENT_PROMPT = (
    "Welcome! Are you a CLIENT or on the TEAM? Reply with your answer and your "
    "email so your identity carries across every channel you message us on, "
    "e.g. 'CLIENT jane@example.com' or 'TEAM jane@example.com' "
    "(or 'TEAM DEV jane@example.com' to name a specific role)."
)


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


def parse_enrollment_answer(text: str) -> tuple[Population, str] | None:
    """Pure: parse 'CLIENT you@x.com' / 'TEAM you@x.com' / 'TEAM DEV you@x.com'.

    Also accepts a bare role ('DEV you@x.com') for people who skip the word
    TEAM. Returns None when the reply doesn't contain both a recognizable
    population and an email.
    """
    stripped = text.strip()
    if not stripped:
        return None

    email_match = _EMAIL_RE.search(stripped)
    if not email_match:
        return None
    email = email_match.group(0)

    head_parts = stripped[: email_match.start()].split()
    if not head_parts:
        return None

    first = head_parts[0].upper()
    if first == "CLIENT":
        return Population.CLIENT, email
    if first == "TEAM":
        if len(head_parts) >= 2 and head_parts[1].upper() in _TEAM_ROLE_ALIASES:
            return _TEAM_ROLE_ALIASES[head_parts[1].upper()], email
        return Population.OPS, email  # least-privileged team default
    if first in _TEAM_ROLE_ALIASES:
        return _TEAM_ROLE_ALIASES[first], email
    return None


def get_pending_enrollment(
    session: Session, *, channel: str, channel_id: str
) -> PendingEnrollment | None:
    """Fetch the in-flight enrollment question for a (channel, channel_id), if any."""
    return (
        session.query(PendingEnrollment)
        .filter(PendingEnrollment.channel == channel, PendingEnrollment.channel_id == channel_id)
        .first()
    )


def start_enrollment(
    session: Session, *, org_id: str, channel: str, channel_id: str, conversation_id: str
) -> PendingEnrollment:
    """Record that we've asked an unknown sender client-vs-team (idempotent)."""
    _ensure_org(session, org_id)
    existing = get_pending_enrollment(session, channel=channel, channel_id=channel_id)
    if existing is not None:
        return existing
    pending = PendingEnrollment(
        id=str(uuid.uuid4()),
        org_id=org_id,
        channel=channel,
        channel_id=channel_id,
        conversation_id=conversation_id,
        created_at=datetime.now(UTC),
    )
    session.add(pending)
    session.commit()
    return pending


def find_or_create_principal_by_email(
    session: Session, *, org_id: str, population: Population, email: str
) -> Principal:
    """Find an existing principal by (org, email), else create one.

    This is the cross-channel identity mechanism: the same email answered on
    a second channel resolves to the same principal instead of minting a new
    one, so one person's identity persists across every channel they use.
    """
    existing = (
        session.query(Principal)
        .filter(Principal.org_id == org_id, Principal.email == email)
        .first()
    )
    if existing is not None:
        return existing
    principal = Principal(
        id=str(uuid.uuid4()),
        org_id=org_id,
        population=population,
        email=email,
        created_at=datetime.now(UTC),
    )
    session.add(principal)
    session.flush()
    return principal


def complete_enrollment(
    session: Session, *, pending: PendingEnrollment, population: Population, email: str
) -> tuple[Principal, ChannelBinding]:
    """Resolve a pending enrollment into a (principal, binding) pair and clear it."""
    principal = find_or_create_principal_by_email(
        session, org_id=pending.org_id, population=population, email=email
    )
    binding = ChannelBinding(
        id=str(uuid.uuid4()),
        principal_id=principal.id,
        channel=pending.channel,
        channel_id=pending.channel_id,
        conversation_id=pending.conversation_id,
        verified="verified",
        created_at=datetime.now(UTC),
    )
    session.add(binding)
    session.delete(pending)
    session.commit()
    return principal, binding
