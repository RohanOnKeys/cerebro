"""Unit tests for the orders ledger service and tools."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population, Principal
from cerebro.registry import TOOLS
from cerebro.services.orders import infer_order_type, open_order


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


def test_free_text_open_creates_order_with_order_type(db_session, client_principal):
    """Free-text open must persist an orders row with order_type set."""
    order = open_order(
        db_session,
        principal=client_principal,
        text="can you get me and priya on a call thursday afternoon",
    )

    assert order.id
    assert order.order_type == "schedule"
    assert order.status == "open"
    assert order.free_text
    assert "priya" in order.free_text


def test_open_order_tool_sets_order_type(db_session, client_principal):
    """Registry open_order tool creates a typed orders row from free text."""
    result = TOOLS["open_order"].handler(
        session=db_session,
        principal=client_principal,
        text="deploy the api to staging",
    )

    assert result["order_type"] == "ci"
    assert result["status"] == "open"
    assert result["id"]


def test_infer_order_type_defaults_to_general():
    """Unrecognized free text maps to general."""
    assert infer_order_type("hello there") == "general"
