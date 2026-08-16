"""Unit tests for services.orgs, especially resolve_active_org - the shared
helper behind both the admin dashboard's org-scoped endpoints and the GitHub
webhook handler. Extracted after a real production bug: the webhook path
hardcoded a "default_org" id that didn't exist once real orgs existed."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Message, Org
from cerebro.services.orgs import resolve_active_org


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _org(session, *, id, created_at):
    org = Org(id=id, name=id, join_code=id.upper(), created_at=created_at)
    session.add(org)
    session.commit()
    return org


def _message(session, *, org_id, created_at):
    session.add(
        Message(
            id=f"msg_{org_id}_{created_at.isoformat()}",
            org_id=org_id,
            principal_id="p_unused",
            channel="telegram",
            population="client",
            role="user",
            content="hi",
            created_at=created_at,
        )
    )
    session.commit()


def test_resolve_active_org_returns_none_when_no_orgs_exist(db_session):
    assert resolve_active_org(db_session) is None


def test_resolve_active_org_falls_back_to_most_recently_created(db_session):
    """No messages yet (e.g. right after create_team, before anyone's
    chatted) - pick the newest org rather than the oldest."""
    _org(db_session, id="older", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _org(db_session, id="newer", created_at=datetime(2026, 6, 1, tzinfo=UTC))

    resolved = resolve_active_org(db_session)

    assert resolved is not None
    assert resolved.id == newer.id


def test_resolve_active_org_prefers_the_org_with_the_most_recent_message(db_session):
    """The real fix: an old org that's still chattering right now beats a
    newer org nobody has messaged in yet."""
    old_but_active = _org(db_session, id="old_active", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    _org(db_session, id="new_quiet", created_at=datetime(2026, 6, 1, tzinfo=UTC))
    _message(db_session, org_id="old_active", created_at=datetime.now(UTC) - timedelta(minutes=1))

    resolved = resolve_active_org(db_session)

    assert resolved is not None
    assert resolved.id == old_but_active.id


def test_resolve_active_org_ignores_a_message_pointing_at_a_deleted_org(db_session):
    """Defensive: a stale Message.org_id that no longer has an Org row
    (shouldn't normally happen, but the FK isn't ON DELETE CASCADE-enforced
    everywhere) must not crash the lookup - just fall through to the
    most-recently-created-org fallback."""
    survivor = _org(db_session, id="survivor", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    _message(db_session, org_id="ghost_org", created_at=datetime.now(UTC))

    resolved = resolve_active_org(db_session)

    assert resolved is not None
    assert resolved.id == survivor.id
