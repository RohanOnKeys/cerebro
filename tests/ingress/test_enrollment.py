import pytest
from datetime import UTC, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population
from cerebro.ingress.enrollment import enroll_unknown_sender


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
def test_org(db_session):
    """Create a test organization."""
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def test_enroll_unknown_sender_telegram(db_session, test_org):
    """Enroll an unknown Telegram sender."""
    principal, binding = enroll_unknown_sender(
        db_session, "org_1", "telegram", "123456789", "conv_abc123"
    )

    assert principal.id is not None
    assert principal.org_id == "org_1"
    assert principal.population == Population.CLIENT
    assert binding.principal_id == principal.id
    assert binding.channel == "telegram"
    assert binding.channel_id == "123456789"
    assert binding.conversation_id == "conv_abc123"
    assert binding.verified == "verified"


def test_enroll_unknown_sender_creates_row_with_conversation_id(db_session, test_org):
    """Enroll should create a channel_bindings row with conversation_id."""
    principal, binding = enroll_unknown_sender(
        db_session, "org_1", "whatsapp", "5551234567", "conv_xyz789"
    )

    assert binding.conversation_id == "conv_xyz789"
    assert binding.channel == "whatsapp"


def test_enroll_multiple_senders(db_session, test_org):
    """Multiple enrollments should create separate principals."""
    principal1, binding1 = enroll_unknown_sender(
        db_session, "org_1", "email", "user1@example.com", "conv_1"
    )
    principal2, binding2 = enroll_unknown_sender(
        db_session, "org_1", "email", "user2@example.com", "conv_2"
    )

    assert principal1.id != principal2.id
    assert binding1.id != binding2.id
