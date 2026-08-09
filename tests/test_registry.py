"""Unit tests for the population-gated tool registry."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population, Principal
from cerebro.registry import TOOLS, TOOLS_FOR, tools_for


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
    """Create a CLIENT principal for handler tests."""
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
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


def test_tools_for_client_excludes_enroll_principal():
    """CLIENT tool list must not include team/ops-only enroll_principal."""
    names = {tool.name for tool in TOOLS_FOR[Population.CLIENT]}

    assert "whoami" in names
    assert "set_availability" in names
    assert "enroll_principal" not in names


def test_tools_for_ops_includes_enroll_principal():
    """OPS (team) tool list includes enroll_principal."""
    names = {tool.name for tool in TOOLS_FOR[Population.OPS]}

    assert "enroll_principal" in names
    assert "whoami" in names
    assert "set_availability" in names


def test_tools_for_helper_matches_mapping():
    """tools_for() mirrors TOOLS_FOR for each population."""
    for population in Population:
        assert tools_for(population) == TOOLS_FOR[population]


def test_enroll_principal_allowed_populations_are_team_only():
    """enroll_principal is gated to OPS/DEV/LEAD/ADMIN only."""
    allowed = TOOLS["enroll_principal"].allowed_populations

    assert Population.CLIENT not in allowed
    assert allowed == frozenset(
        {Population.OPS, Population.DEV, Population.LEAD, Population.ADMIN}
    )


def test_whoami_handler_returns_identity(client_principal):
    """whoami handler returns principal identity fields."""
    result = TOOLS["whoami"].handler(principal=client_principal)

    assert result["principal_id"] == "principal_client"
    assert result["population"] == Population.CLIENT.value
    assert result["org_id"] == "org_1"
    assert result["email"] == "client@test.com"


def test_set_availability_handler(client_principal):
    """set_availability handler acknowledges availability for a principal."""
    result = TOOLS["set_availability"].handler(
        principal=client_principal, available=False, note="out of office"
    )

    assert result["principal_id"] == "principal_client"
    assert result["available"] is False
    assert result["note"] == "out of office"
    assert result["status"] == "recorded"


def test_enroll_principal_handler_uses_enrollment_service(db_session, client_principal):
    """enroll_principal handler wraps enroll_unknown_sender."""
    # client_principal fixture ensures org_1 exists
    _ = client_principal
    result = TOOLS["enroll_principal"].handler(
        session=db_session,
        org_id="org_1",
        channel="telegram",
        channel_id="999888",
        conversation_id="conv_registry_1",
    )

    assert result["population"] == Population.CLIENT.value
    assert result["verified"] == "pending"
    assert result["principal_id"]
    assert result["binding_id"]
