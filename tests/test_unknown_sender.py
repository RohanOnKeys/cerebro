"""Unit tests for main.handle_unknown_sender: ask client-vs-team, then enroll."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, ChannelBinding, Principal
from cerebro.ingress.enrollment import ENROLLMENT_PROMPT
from cerebro.ingress.principals import resolve_principal
from cerebro.main import handle_unknown_sender


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_first_message_asks_client_vs_team(db_session):
    reply = handle_unknown_sender(db_session, "telegram", "tg_1", "hi there")

    assert reply == ENROLLMENT_PROMPT
    assert db_session.query(Principal).count() == 0


def test_second_message_with_valid_answer_enrolls(db_session):
    handle_unknown_sender(db_session, "telegram", "tg_1", "hi there")

    reply = handle_unknown_sender(db_session, "telegram", "tg_1", "CLIENT jane@example.com")

    assert "enrolled as client" in reply.lower()
    principal = db_session.query(Principal).one()
    assert principal.email == "jane@example.com"
    binding = db_session.query(ChannelBinding).one()
    assert binding.principal_id == principal.id
    assert binding.channel == "telegram"


def test_unparseable_answer_reprompts_without_enrolling(db_session):
    handle_unknown_sender(db_session, "telegram", "tg_1", "hi there")

    reply = handle_unknown_sender(db_session, "telegram", "tg_1", "uhh what?")

    assert "didn't catch that" in reply.lower()
    assert db_session.query(Principal).count() == 0


def test_resolve_principal_works_after_enrollment_completes(db_session):
    handle_unknown_sender(db_session, "telegram", "tg_1", "hi there")
    handle_unknown_sender(db_session, "telegram", "tg_1", "CLIENT jane@example.com")

    principal = resolve_principal(db_session, "telegram", "tg_1")

    assert principal is not None
    assert principal.population.value == "client"


def test_dev_claim_lands_at_ops_pending_approval(db_session):
    """A gated role claim (DEV/LEAD/ADMIN) doesn't take effect until approved."""
    handle_unknown_sender(db_session, "telegram", "tg_1", "hi there")

    reply = handle_unknown_sender(db_session, "telegram", "tg_1", "DEV jane@example.com")

    assert "pending approval" in reply.lower()
    principal = resolve_principal(db_session, "telegram", "tg_1")
    assert principal is not None
    assert principal.population.value == "ops"


def test_identity_persists_across_channels_via_matching_email(db_session):
    """Jane enrolls on Telegram, then messages Discord for the first time - same identity."""
    handle_unknown_sender(db_session, "telegram", "tg_1", "hi")
    handle_unknown_sender(db_session, "telegram", "tg_1", "CLIENT jane@example.com")
    telegram_principal = resolve_principal(db_session, "telegram", "tg_1")

    handle_unknown_sender(db_session, "discord", "dc_1", "hello")
    handle_unknown_sender(db_session, "discord", "dc_1", "CLIENT jane@example.com")
    discord_principal = resolve_principal(db_session, "discord", "dc_1")

    assert telegram_principal.id == discord_principal.id
    assert db_session.query(Principal).count() == 1
    assert db_session.query(ChannelBinding).count() == 2
