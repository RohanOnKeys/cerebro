"""Unit tests for the free-text -> cortex tool-loop fallback in main.py."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import cerebro.main as main_module
from cerebro.db.models import Base, Org, Population, Principal
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
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
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

    reply = handle_free_text("hello there", client_principal, db_session)

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

    reply = handle_free_text("who am i?", client_principal, db_session)

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

    reply = handle_free_text("keep going forever", client_principal, db_session)

    assert "more steps" in reply.lower()


def test_upstream_http_error_returns_a_friendly_message_not_a_crash(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient(error=httpx.HTTPStatusError("boom", request=None, response=None))
    _patch_client(monkeypatch, client)

    reply = handle_free_text("do something", client_principal, db_session)

    assert "couldn't reach the model" in reply.lower()


def test_upstream_value_error_returns_a_friendly_message_not_a_crash(
    db_session, client_principal, monkeypatch
):
    client = ScriptedClient(error=ValueError("Featherless response contained no choices"))
    _patch_client(monkeypatch, client)

    reply = handle_free_text("do something", client_principal, db_session)

    assert "couldn't reach the model" in reply.lower()


def test_blank_final_content_falls_back_to_done(db_session, client_principal, monkeypatch):
    client = ScriptedClient([{"role": "assistant", "content": "   "}])
    _patch_client(monkeypatch, client)

    reply = handle_free_text("ok thanks", client_principal, db_session)

    assert reply == "Done."


def test_get_chat_client_is_memoized(monkeypatch):
    monkeypatch.setattr(main_module, "_chat_client", None)
    first = main_module._get_chat_client()
    second = main_module._get_chat_client()
    assert first is second
    monkeypatch.setattr(main_module, "_chat_client", None)
