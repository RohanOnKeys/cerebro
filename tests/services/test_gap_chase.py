"""Unit tests for the gap chase clock job."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import (
    Base,
    GapChase,
    GapChaseStatus,
    NudgeKind,
    Org,
    Population,
    Principal,
)
from cerebro.services.gap_chase import process_due_gap_chases
from cerebro.services.gap_harvester import BACKOFF_MINUTES
from cerebro.services.nudges import list_nudges
from cerebro.services.orders import open_order


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client_principal(db_session):
    """Create a CLIENT principal."""
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    principal = Principal(
        id="principal_client",
        org_id="org_1",
        population=Population.CLIENT,
        email="client@test.com",
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def _order_with_email_gap(db_session, client_principal):
    return open_order(
        db_session,
        principal=client_principal,
        text="please help with this general request",
        order_type="general",
        fields={},
    )


def test_one_follow_up_question(db_session, client_principal):
    """First due tick emits one follow-up question nudge."""
    order = _order_with_email_gap(db_session, client_principal)
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    actions = process_due_gap_chases(db_session, now=now)

    assert len(actions) == 1
    assert actions[0]["action"] == "ask"
    assert actions[0]["field_name"] == "email"
    assert actions[0]["ask_count"] == 1
    nudges = list_nudges(db_session, order_id=order.id, kind=NudgeKind.GAP_ASK.value)
    assert len(nudges) == 1
    assert "email" in nudges[0].body


def test_second_attempt_respects_backoff(db_session, client_principal):
    """A second job tick before backoff elapses must not ask again."""
    order = _order_with_email_gap(db_session, client_principal)
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    first = process_due_gap_chases(db_session, now=now)
    second = process_due_gap_chases(db_session, now=now + timedelta(minutes=1))

    assert len(first) == 1
    assert second == []
    chase = (
        db_session.query(GapChase)
        .filter(GapChase.order_id == order.id, GapChase.field_name == "email")
        .one()
    )
    assert chase.ask_count == 1
    expected_next = (now + timedelta(minutes=BACKOFF_MINUTES[1])).replace(tzinfo=None)
    assert chase.next_ask_at.replace(tzinfo=None) == expected_next

    third = process_due_gap_chases(
        db_session, now=now + timedelta(minutes=BACKOFF_MINUTES[1])
    )
    assert len(third) == 1
    assert third[0]["action"] == "ask"
    assert third[0]["ask_count"] == 2


def test_fourth_attempt_abandons_and_escalates(db_session, client_principal):
    """The fourth due attempt abandons the chase and creates an escalation nudge."""
    order = _order_with_email_gap(db_session, client_principal)
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    for _ in range(3):
        actions = process_due_gap_chases(db_session, now=now)
        assert len(actions) == 1
        assert actions[0]["action"] == "ask"
        chase = (
            db_session.query(GapChase)
            .filter(GapChase.order_id == order.id, GapChase.field_name == "email")
            .one()
        )
        now = chase.next_ask_at or (now + timedelta(days=3))

    final = process_due_gap_chases(db_session, now=now)
    assert len(final) == 1
    assert final[0]["action"] == "escalate"
    assert final[0]["chase_status"] == GapChaseStatus.EXHAUSTED.value
    assert final[0]["ask_count"] == 4

    asks = list_nudges(db_session, order_id=order.id, kind=NudgeKind.GAP_ASK.value)
    escalations = list_nudges(
        db_session, order_id=order.id, kind=NudgeKind.GAP_ESCALATE.value
    )
    assert len(asks) == 3
    assert len(escalations) == 1
    assert "abandoned" in escalations[0].body.lower() or "Escalation" in escalations[0].body
