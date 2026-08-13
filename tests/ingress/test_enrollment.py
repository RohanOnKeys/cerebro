import pytest
from datetime import UTC, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, PendingEnrollment, Population
from cerebro.ingress.enrollment import (
    complete_enrollment,
    enroll_unknown_sender,
    find_or_create_principal_by_email,
    get_pending_enrollment,
    parse_enrollment_answer,
    start_enrollment,
)


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
        db_session, "org_1", "discord", "5551234567", "conv_xyz789"
    )

    assert binding.conversation_id == "conv_xyz789"
    assert binding.channel == "discord"


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


# --- parse_enrollment_answer (pure) ---


def test_parse_client_answer():
    assert parse_enrollment_answer("CLIENT jane@example.com") == (
        Population.CLIENT,
        "jane@example.com",
    )


def test_parse_team_answer_defaults_to_ops():
    assert parse_enrollment_answer("TEAM jane@example.com") == (Population.OPS, "jane@example.com")


def test_parse_team_with_specific_role():
    assert parse_enrollment_answer("TEAM DEV jane@example.com") == (
        Population.DEV,
        "jane@example.com",
    )


def test_parse_bare_role_without_team_prefix():
    assert parse_enrollment_answer("LEAD jane@example.com") == (
        Population.LEAD,
        "jane@example.com",
    )


def test_parse_answer_is_case_insensitive():
    assert parse_enrollment_answer("client JANE@example.com") == (
        Population.CLIENT,
        "JANE@example.com",
    )


def test_parse_answer_missing_email_returns_none():
    assert parse_enrollment_answer("CLIENT") is None


def test_parse_answer_unrecognized_role_returns_none():
    assert parse_enrollment_answer("PIRATE jane@example.com") is None


def test_parse_answer_empty_text_returns_none():
    assert parse_enrollment_answer("") is None


# --- start_enrollment / get_pending_enrollment ---


def test_start_enrollment_is_idempotent(db_session, test_org):
    """A second unanswered message from the same sender doesn't duplicate the row."""
    first = start_enrollment(
        db_session, org_id="org_1", channel="telegram", channel_id="t1", conversation_id="c1"
    )
    second = start_enrollment(
        db_session, org_id="org_1", channel="telegram", channel_id="t1", conversation_id="c1"
    )

    assert first.id == second.id
    assert db_session.query(PendingEnrollment).count() == 1


def test_get_pending_enrollment_returns_none_when_absent(db_session, test_org):
    assert get_pending_enrollment(db_session, channel="telegram", channel_id="nobody") is None


# --- cross-channel identity: find_or_create_principal_by_email ---


def test_find_or_create_principal_by_email_creates_once(db_session, test_org):
    principal = find_or_create_principal_by_email(
        db_session, org_id="org_1", population=Population.CLIENT, email="jane@example.com"
    )

    assert principal.email == "jane@example.com"
    assert principal.population == Population.CLIENT


def test_find_or_create_principal_by_email_reuses_existing(db_session, test_org):
    """The core cross-channel mechanism: same email -> same principal, not a new one."""
    first = find_or_create_principal_by_email(
        db_session, org_id="org_1", population=Population.CLIENT, email="jane@example.com"
    )
    second = find_or_create_principal_by_email(
        db_session, org_id="org_1", population=Population.CLIENT, email="jane@example.com"
    )

    assert first.id == second.id


def test_complete_enrollment_second_channel_binds_to_same_principal(db_session, test_org):
    """Jane enrolls on Telegram, then answers again on Discord with the same email."""
    telegram_pending = start_enrollment(
        db_session, org_id="org_1", channel="telegram", channel_id="tg_1", conversation_id="c1"
    )
    telegram_principal, telegram_binding, _claim = complete_enrollment(
        db_session, pending=telegram_pending, population=Population.CLIENT, email="jane@example.com"
    )

    discord_pending = start_enrollment(
        db_session, org_id="org_1", channel="discord", channel_id="dc_1", conversation_id="c2"
    )
    discord_principal, discord_binding, _claim = complete_enrollment(
        db_session, pending=discord_pending, population=Population.CLIENT, email="jane@example.com"
    )

    assert discord_principal.id == telegram_principal.id
    assert discord_binding.principal_id == telegram_binding.principal_id
    assert discord_binding.channel == "discord"
    assert telegram_binding.channel == "telegram"


def test_complete_enrollment_clears_the_pending_row(db_session, test_org):
    pending = start_enrollment(
        db_session, org_id="org_1", channel="telegram", channel_id="tg_2", conversation_id="c3"
    )

    complete_enrollment(db_session, pending=pending, population=Population.CLIENT, email="a@b.com")

    assert get_pending_enrollment(db_session, channel="telegram", channel_id="tg_2") is None
