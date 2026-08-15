"""Unit tests for the relay_to_population tool (registry + membrane integration)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Crossing, Org, Population, Principal
from cerebro.membrane.policy import seed_default_policies
from cerebro.registry import TOOLS
from cerebro.services.orders import open_order


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_default_policies(session)
    yield session
    session.close()


@pytest.fixture
def org(db_session):
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def _principal(db_session, org, *, id, population):
    principal = Principal(id=id, org_id=org.id, population=population, created_at=datetime.now(UTC))
    db_session.add(principal)
    db_session.commit()
    return principal


def test_relay_redacts_dev_to_client_text(db_session, org):
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)

    result = TOOLS["relay_to_population"].handler(
        session=db_session,
        principal=dev,
        target_population="client",
        text="summary: shipped\nstack_trace: boom\nestimate: 2h",
    )

    assert result["action"] == "redact"
    assert "stack_trace" not in result["content"]
    assert "estimate" not in result["content"]
    assert "summary: shipped" in result["content"]


def test_relay_denies_admin_to_client(db_session, org):
    admin = _principal(db_session, org, id="p_admin", population=Population.ADMIN)

    result = TOOLS["relay_to_population"].handler(
        session=db_session, principal=admin, target_population="client", text="internal notes"
    )

    assert result["error"] == "relay_denied"
    crossing = db_session.query(Crossing).filter(Crossing.id == result["crossing_id"]).one()
    assert crossing.status == "denied"


def test_relay_records_crossing_before_content_is_resolved(db_session, org):
    """A crossing row must exist even when relay ultimately denies."""
    admin = _principal(db_session, org, id="p_admin", population=Population.ADMIN)

    before = db_session.query(Crossing).count()
    TOOLS["relay_to_population"].handler(
        session=db_session, principal=admin, target_population="client", text="x"
    )
    after = db_session.query(Crossing).count()

    assert after == before + 1


def test_relay_allows_client_to_dev_unredacted(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)

    result = TOOLS["relay_to_population"].handler(
        session=db_session, principal=client, target_population="dev", text="please help with X"
    )

    assert result["action"] == "allow"
    assert result["content"] == "please help with X"


def test_relay_pulls_order_digest_when_order_id_given(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    order = open_order(db_session, principal=client, text="summary request", order_type="summary")
    from cerebro.services.orders import dumps_fields

    order.fields_json = dumps_fields({"digest": "summary: done\nstack_trace: x\nestimate: 1h"})
    db_session.commit()

    result = TOOLS["relay_to_population"].handler(
        session=db_session, principal=dev, target_population="client", order_id=order.id
    )

    assert "stack_trace" not in result["content"]
    assert "summary: done" in result["content"]
