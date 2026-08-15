"""Unit tests for the free-text -> cortex tool-loop fallback in main.py."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import cerebro.main as main_module
from cerebro.db.models import Base, Message, Org, Population, Principal
from cerebro.main import handle_free_text


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client_principal(db_session):
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    principal = Principal(
        id="p_client",
        org_id="org_1",
        population=Population.CLIENT,
        email="client@test.com",
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()
    return principal


@pytest.fixture
def dev_principal(db_session):
    principal = Principal(
        id="p_dev",
        org_id="org_1",
        population=Population.DEV,
        email="dev@test.com",
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()
    return principal


class ScriptedClient:
    """Fake chat client returning scripted assistant messages, or raising."""

    def __init__(self, responses: list[dict[str, Any]] | None = None, error: Exception | None = None):
        self._responses = list(responses or [])
        self._error = error
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, messages, *, tools=None, tool_choice=None):
        self.calls.append(messages)
        if self._error is not None:
            raise self._error
        return self._responses.pop(0)


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(main_module, "_get_chat_client", lambda: client)


def test_free_text_with_no_tool_calls_returns_final_content(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient([{"role": "assistant", "content": "Hey, how can I help?"}])
    _patch_client(monkeypatch, client)

    reply = handle_free_text("hello there", client_principal, db_session, "telegram")

    assert reply == "Hey, how can I help?"
    # The user's message reached the model as-is.
    assert client.calls[0][-1] == {"role": "user", "content": "hello there"}


def test_free_text_executes_a_tool_call_then_returns_the_final_reply(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "whoami", "arguments": "{}"},
                    }
                ],
            },
            {"role": "assistant", "content": "You are p_client (client)."},
        ]
    )
    _patch_client(monkeypatch, client)

    reply = handle_free_text("who am i?", client_principal, db_session, "telegram")

    assert reply == "You are p_client (client)."
    assert len(client.calls) == 2


def test_tool_round_limit_exceeded_returns_a_friendly_message(
    db_session, client_principal, monkeypatch
):
    looping_call = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "whoami", "arguments": "{}"}}
        ],
    }
    client = ScriptedClient([looping_call] * 10)
    _patch_client(monkeypatch, client)

    reply = handle_free_text("keep going forever", client_principal, db_session, "telegram")

    assert "more steps" in reply.lower()


def test_upstream_http_error_returns_a_friendly_message_not_a_crash(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient(error=httpx.HTTPStatusError("boom", request=None, response=None))
    _patch_client(monkeypatch, client)

    reply = handle_free_text("do something", client_principal, db_session, "telegram")

    assert "couldn't reach the model" in reply.lower()


def test_upstream_value_error_returns_a_friendly_message_not_a_crash(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient(error=ValueError("Featherless response contained no choices"))
    _patch_client(monkeypatch, client)

    reply = handle_free_text("do something", client_principal, db_session, "telegram")

    assert "couldn't reach the model" in reply.lower()


def test_blank_final_content_falls_back_to_done(db_session, client_principal, monkeypatch):
    client = ScriptedClient([{"role": "assistant", "content": "   "}])
    _patch_client(monkeypatch, client)

    reply = handle_free_text("ok thanks", client_principal, db_session, "telegram")

    assert reply == "Done."


def test_get_chat_client_is_memoized(monkeypatch):
    monkeypatch.setattr(main_module, "_chat_client", None)
    first = main_module._get_chat_client()
    second = main_module._get_chat_client()
    assert first is second
    monkeypatch.setattr(main_module, "_chat_client", None)


# --- Message ledger: user id + population type embedded, persisted memory ---


def test_handle_free_text_persists_user_and_assistant_turns_with_id_and_type(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient([{"role": "assistant", "content": "Sure, happy to help."}])
    _patch_client(monkeypatch, client)

    handle_free_text("can you help me?", client_principal, db_session, "telegram")

    rows = db_session.query(Message).order_by(Message.created_at.asc()).all()
    assert [r.role for r in rows] == ["user", "assistant"]
    assert all(r.principal_id == "p_client" for r in rows)
    assert all(r.population == "client" for r in rows)
    assert all(r.channel == "telegram" for r in rows)
    assert rows[0].content == "can you help me?"
    assert rows[1].content == "Sure, happy to help."


def test_second_call_sends_prior_turns_as_history_to_the_model(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient(
        [
            {"role": "assistant", "content": "Got it, what's the topic?"},
            {"role": "assistant", "content": "Noted."},
        ]
    )
    _patch_client(monkeypatch, client)

    handle_free_text("I want to open an order", client_principal, db_session, "telegram")
    handle_free_text("it's about billing", client_principal, db_session, "telegram")

    second_call_messages = client.calls[1]
    contents = [m["content"] for m in second_call_messages]
    assert "I want to open an order" in contents
    assert "Got it, what's the topic?" in contents
    assert contents[-1] == "it's about billing"


def test_history_is_scoped_per_principal(db_session, client_principal, dev_principal, monkeypatch):
    client = ScriptedClient(
        [
            {"role": "assistant", "content": "client reply"},
            {"role": "assistant", "content": "dev reply"},
        ]
    )
    _patch_client(monkeypatch, client)

    handle_free_text("client message", client_principal, db_session, "telegram")
    handle_free_text("dev message", dev_principal, db_session, "discord")

    dev_call_messages = client.calls[1]
    contents = [m["content"] for m in dev_call_messages]
    assert "client message" not in contents
    assert contents[-1] == "dev message"
