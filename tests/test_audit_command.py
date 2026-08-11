"""Unit tests for the AUDIT command wired into main.execute_command."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population, Principal
from cerebro.ingress.commands import parse_command
from cerebro.main import execute_command
from cerebro.membrane.crossings import record_crossing


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def org(db_session):
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def _principal(db_session, org, *, id, population):
    principal = Principal(id=id, org_id=org.id, population=population, created_at=datetime.now(UTC))
    db_session.add(principal)
    db_session.commit()
    return principal


def test_audit_denied_for_client(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)

    reply = execute_command(parse_command("AUDIT"), client, db_session)

    assert "not available" in reply.lower()


def test_audit_lists_crossings_for_team_member(db_session, org):
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    record_crossing(
        db_session,
        org_id=org.id,
        principal_id=dev.id,
        source="dev",
        target="client",
        action="redact",
    )

    reply = execute_command(parse_command("AUDIT"), dev, db_session)

    assert "dev->client redact" in reply


def test_audit_with_no_crossings_says_so(db_session, org):
    lead = _principal(db_session, org, id="p_lead", population=Population.LEAD)

    reply = execute_command(parse_command("AUDIT"), lead, db_session)

    assert "no crossings" in reply.lower()
