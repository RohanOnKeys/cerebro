import pytest
from datetime import UTC, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, PendingEnrollment, Population
from cerebro.ingress.enrollment import (
    apply_join_code,
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
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def _start_and_code(db_session, *, channel: str, channel_id: str, conversation_id: str, code: str = "TESTORG"):
    """Helper: run stage 1 (start_enrollment + apply_join_code) so tests
    that only care about stage 2 (complete_enrollment) don't have to repeat
    the code round trip inline."""
    pending = start_enrollment(
        db_session, channel=channel, channel_id=channel_id, conversation_id=conversation_id
    )
    return apply_join_code(db_session, pending=pending, code=code)


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


def test_parse_default_answer_is_client_with_name():
    """No leading keyword: defaults to CLIENT, name is everything before the email."""
    assert parse_enrollment_answer("Jane Doe jane@example.com") == (
        Population.CLIENT,
        "jane@example.com",
        "Jane Doe",
    )


def test_parse_default_answer_accepts_comma_before_email():
    assert parse_enrollment_answer("Jane Doe, jane@example.com") == (
        Population.CLIENT,
        "jane@example.com",
        "Jane Doe",
    )


def test_parse_explicit_client_keyword_with_name():
    assert parse_enrollment_answer("CLIENT Jane Doe jane@example.com") == (
        Population.CLIENT,
        "jane@example.com",
        "Jane Doe",
    )


def test_parse_client_keyword_without_name_returns_none():
    """CLIENT is only useful alongside a name now - bare 'CLIENT <email>' has
    nothing to use as display_name, so it's treated the same as missing input."""
    assert parse_enrollment_answer("CLIENT jane@example.com") is None


def test_parse_answer_with_no_name_text_returns_none():
    assert parse_enrollment_answer("jane@example.com") is None


def test_parse_team_answer_defaults_to_ops():
    assert parse_enrollment_answer("TEAM jane@example.com") == (
        Population.OPS,
        "jane@example.com",
        "",
    )


def test_parse_team_with_specific_role():
    assert parse_enrollment_answer("TEAM DEV jane@example.com") == (
        Population.DEV,
        "jane@example.com",
        "",
    )


def test_parse_bare_role_without_team_prefix():
    assert parse_enrollment_answer("LEAD jane@example.com") == (
        Population.LEAD,
        "jane@example.com",
        "",
    )


def test_parse_answer_is_case_insensitive():
    assert parse_enrollment_answer("team JANE@example.com") == (
        Population.OPS,
        "JANE@example.com",
        "",
    )


def test_parse_answer_missing_email_returns_none():
    assert parse_enrollment_answer("CLIENT") is None


def test_parse_unrecognized_word_is_treated_as_a_name_not_a_role():
    """Anything that isn't TEAM/a role keyword falls through to the default
    CLIENT-with-name path, same as any other name - 'Pirate' is as valid a
    first name as 'Jane'."""
    assert parse_enrollment_answer("Pirate jane@example.com") == (
        Population.CLIENT,
        "jane@example.com",
        "Pirate",
    )


def test_parse_answer_empty_text_returns_none():
    assert parse_enrollment_answer("") is None


# --- start_enrollment / get_pending_enrollment ---


def test_start_enrollment_is_idempotent(db_session, test_org):
    """A second unanswered message from the same sender doesn't duplicate the row."""
    first = start_enrollment(
        db_session, channel="telegram", channel_id="t1", conversation_id="c1"
    )
    second = start_enrollment(
        db_session, channel="telegram", channel_id="t1", conversation_id="c1"
    )

    assert first.id == second.id
    assert db_session.query(PendingEnrollment).count() == 1
    assert first.stage == "awaiting_code"
    assert first.org_id is None


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
    telegram_pending = _start_and_code(
        db_session, channel="telegram", channel_id="tg_1", conversation_id="c1"
    )
    telegram_principal, telegram_binding, _claim = complete_enrollment(
        db_session, pending=telegram_pending, population=Population.CLIENT, email="jane@example.com"
    )

    discord_pending = _start_and_code(
        db_session, channel="discord", channel_id="dc_1", conversation_id="c2"
    )
    discord_principal, discord_binding, _claim = complete_enrollment(
        db_session, pending=discord_pending, population=Population.CLIENT, email="jane@example.com"
    )

    assert discord_principal.id == telegram_principal.id
    assert discord_binding.principal_id == telegram_binding.principal_id
    assert discord_binding.channel == "discord"
    assert telegram_binding.channel == "telegram"


def test_complete_enrollment_stores_the_captured_name(db_session, test_org):
    pending = _start_and_code(
        db_session, channel="telegram", channel_id="tg_name", conversation_id="c_name"
    )

    principal, _binding, _claim = complete_enrollment(
        db_session,
        pending=pending,
        population=Population.CLIENT,
        email="jane@example.com",
        name="Jane Doe",
    )

    assert principal.display_name == "Jane Doe"


def test_complete_enrollment_clears_the_pending_row(db_session, test_org):
    pending = _start_and_code(
        db_session, channel="telegram", channel_id="tg_2", conversation_id="c3"
    )

    complete_enrollment(db_session, pending=pending, population=Population.CLIENT, email="a@b.com")

    assert get_pending_enrollment(db_session, channel="telegram", channel_id="tg_2") is None


# --- team code stage: apply_join_code / is_plausible_code ---


def test_apply_join_code_resolves_existing_org(db_session, test_org):
    pending = start_enrollment(
        db_session, channel="telegram", channel_id="t9", conversation_id="c9"
    )

    updated = apply_join_code(db_session, pending=pending, code="testorg")

    assert updated.org_id == "org_1"
    assert updated.stage == "awaiting_usertype"


def test_apply_join_code_creates_org_for_unrecognized_code(db_session):
    pending = start_enrollment(
        db_session, channel="telegram", channel_id="t10", conversation_id="c10"
    )

    updated = apply_join_code(db_session, pending=pending, code="NEWTEAM")

    org = db_session.query(Org).filter(Org.join_code == "NEWTEAM").one()
    assert updated.org_id == org.id
    assert org.name == "Team NEWTEAM"


def test_apply_join_code_normalizes_case(db_session, test_org):
    """A second sender typing the code in a different case still lands in
    the same org rather than minting a duplicate."""
    first_pending = start_enrollment(
        db_session, channel="telegram", channel_id="t11", conversation_id="c11"
    )
    second_pending = start_enrollment(
        db_session, channel="discord", channel_id="d11", conversation_id="c12"
    )

    apply_join_code(db_session, pending=first_pending, code="testorg")
    apply_join_code(db_session, pending=second_pending, code="TestOrg")

    assert first_pending.org_id == second_pending.org_id == "org_1"
    assert db_session.query(Org).count() == 1


def test_is_plausible_code_rejects_ordinary_greetings():
    from cerebro.ingress.enrollment import is_plausible_code

    assert is_plausible_code("hi there") is False
    assert is_plausible_code("") is False
    assert is_plausible_code("TESTORG") is True
    assert is_plausible_code("new-team-1") is True
