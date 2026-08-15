import pytest
from datetime import UTC, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Principal, ChannelBinding, Population
from cerebro.ingress.principals import resolve_principal, touch_binding


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
def test_org_and_principal(db_session):
    """Create a test org and principal."""
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()

    principal = Principal(
        id="principal_1",
        org_id="org_1",
        population=Population.DEV,
        email="dev@test.com",
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()

    return org, principal


def test_resolve_principal_hit(db_session, test_org_and_principal):
    """Resolve principal should find a verified binding."""
    org, principal = test_org_and_principal

    binding = ChannelBinding(
        id="binding_1",
        principal_id="principal_1",
        channel="telegram",
        channel_id="123456",
        verified="verified",
        created_at=datetime.now(UTC),
    )
    db_session.add(binding)
    db_session.commit()

    result = resolve_principal(db_session, "telegram", "123456")
    assert result is not None
    assert result.id == "principal_1"


def test_resolve_principal_miss_no_binding(db_session, test_org_and_principal):
    """Resolve principal should return None if binding doesn't exist."""
    result = resolve_principal(db_session, "telegram", "999999")
    assert result is None


def test_resolve_principal_miss_unverified(db_session, test_org_and_principal):
    """Resolve principal should return None if binding is not verified."""
    binding = ChannelBinding(
        id="binding_2",
        principal_id="principal_1",
        channel="slack",
        channel_id="U123456",
        verified="pending",
        created_at=datetime.now(UTC),
    )
    db_session.add(binding)
    db_session.commit()

    result = resolve_principal(db_session, "slack", "U123456")
    assert result is None


def test_touch_binding_create_new(db_session, test_org_and_principal):
    """Touch binding should create a new binding if it doesn't exist."""
    binding = touch_binding(db_session, "principal_1", "discord", "user_123")

    assert binding.id is not None
    assert binding.principal_id == "principal_1"
    assert binding.channel == "discord"
    assert binding.channel_id == "user_123"
    assert binding.verified == "pending"


def test_touch_binding_returns_existing(db_session, test_org_and_principal):
    """Touch binding should return existing binding without creating a new one."""
    binding1 = touch_binding(db_session, "principal_1", "email", "test@example.com")
    binding2 = touch_binding(db_session, "principal_1", "email", "test@example.com")

    assert binding1.id == binding2.id
