"""Unit tests for the persisted per-principal message ledger."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population, Principal
from cerebro.services.messages import (
    HISTORY_WINDOW,
    recent_messages,
    record_message,
    to_chat_messages,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def dev_principal(db_session):
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
    db_session.add(org)
    principal = Principal(
        id="p_dev", org_id="org_1", population=Population.DEV, created_at=datetime.now(UTC)
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def test_record_message_embeds_principal_id_and_population_type(db_session, dev_principal):
    message = record_message(
        db_session, principal=dev_principal, channel="discord", role="user", content="hi"
    )

    assert message.principal_id == "p_dev"
    assert message.population == "dev"
    assert message.channel == "discord"
    assert message.role == "user"
    assert message.content == "hi"


def test_recent_messages_returns_oldest_first(db_session, dev_principal):
    for i in range(3):
        record_message(
            db_session, principal=dev_principal, channel="discord", role="user", content=f"m{i}"
        )

    rows = recent_messages(db_session, principal_id=dev_principal.id)

    assert [r.content for r in rows] == ["m0", "m1", "m2"]


def test_recent_messages_caps_at_the_history_window(db_session, dev_principal):
    for i in range(HISTORY_WINDOW + 5):
        record_message(
            db_session, principal=dev_principal, channel="discord", role="user", content=f"m{i}"
        )

    rows = recent_messages(db_session, principal_id=dev_principal.id)

    assert len(rows) == HISTORY_WINDOW
    assert rows[-1].content == f"m{HISTORY_WINDOW + 4}"


def test_to_chat_messages_produces_role_content_dicts(db_session, dev_principal):
    record_message(
        db_session, principal=dev_principal, channel="discord", role="user", content="hi"
    )
    rows = recent_messages(db_session, principal_id=dev_principal.id)

    assert to_chat_messages(rows) == [{"role": "user", "content": "hi"}]
