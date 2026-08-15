"""Unit tests for the crossing audit ledger: recorded before send, not after."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Crossing, CrossingStatus, Org, Population, Principal
from cerebro.membrane.crossings import (
    list_crossings,
    mark_crossing_sent,
    record_crossing,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def dev(db_session):
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    principal = Principal(
        id="p_dev", org_id="org_1", population=Population.DEV, created_at=datetime.now(UTC)
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def test_record_crossing_persists_before_any_send_happens(db_session, dev):
    """The row must exist as soon as record_crossing returns - before send."""
    crossing = record_crossing(
        db_session,
        org_id=dev.org_id,
        principal_id=dev.id,
        source=dev.population,
        target="client",
        action="redact",
    )

    # Re-fetch independently: proves it was committed, not just held in memory.
    persisted = db_session.query(Crossing).filter(Crossing.id == crossing.id).one()
    assert persisted.status == CrossingStatus.RECORDED.value
    assert persisted.sent_at is None


def test_mark_crossing_sent_updates_status_and_timestamp(db_session, dev):
    crossing = record_crossing(
        db_session,
        org_id=dev.org_id,
        principal_id=dev.id,
        source=dev.population,
        target="client",
        action="redact",
    )

    sent = mark_crossing_sent(db_session, crossing.id)

    assert sent.status == CrossingStatus.SENT.value
    assert sent.sent_at is not None


def test_a_denied_crossing_is_recorded_as_denied_not_sendable(db_session, dev):
    crossing = record_crossing(
        db_session,
        org_id=dev.org_id,
        principal_id=dev.id,
        source="admin",
        target="client",
        action="deny",
    )

    assert crossing.status == CrossingStatus.DENIED.value

    # Attempting to mark a denied crossing sent is a no-op, not a status flip.
    unchanged = mark_crossing_sent(db_session, crossing.id)
    assert unchanged.status == CrossingStatus.DENIED.value
    assert unchanged.sent_at is None


def test_list_crossings_scoped_to_org_newest_first(db_session, dev):
    first = record_crossing(
        db_session, org_id=dev.org_id, principal_id=dev.id, source="dev", target="client", action="redact"
    )
    second = record_crossing(
        db_session, org_id=dev.org_id, principal_id=dev.id, source="client", target="dev", action="allow"
    )

    rows = list_crossings(db_session, org_id=dev.org_id)

    assert [row.id for row in rows] == [second.id, first.id]
