"""Unit tests for the capped tool-calling loop (mocked LLM)."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import cerebro.registry as registry_mod
from cerebro.cortex.loop import ToolRoundLimitExceeded, run_tool_loop
from cerebro.cortex.prompts import assemble_system_prompt
from cerebro.db.models import Base, Org, Population, Principal


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
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
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


class ScriptedClient:
    """Fake chat client that returns scripted assistant messages."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the next scripted assistant message."""
        self.calls.append(
            {"messages": messages, "tools": tools, "tool_choice": tool_choice}
        )
        if not self._responses:
            raise AssertionError("ScriptedClient has no more responses")
        return self._responses.pop(0)


def test_forced_two_tool_response_executes_both_handlers(client_principal, monkeypatch):
    """A single model response with two tool_calls must execute both handlers."""
    whoami_mock = MagicMock(
        side_effect=lambda **kwargs: {
            "principal_id": kwargs["principal"].id,
            "population": kwargs["principal"].population.value,
            "org_id": kwargs["principal"].org_id,
            "email": kwargs["principal"].email or "",
        }
    )
    availability_mock = MagicMock(
        side_effect=lambda **kwargs: {
            "principal_id": kwargs["principal"].id,
            "available": kwargs["available"],
            "note": kwargs.get("note", ""),
            "status": "recorded",
        }
    )

    monkeypatch.setitem(
        registry_mod.TOOLS,
        "whoami",
        replace(registry_mod.TOOLS["whoami"], handler=whoami_mock),
    )
    monkeypatch.setitem(
        registry_mod.TOOLS,
        "set_availability",
        replace(registry_mod.TOOLS["set_availability"], handler=availability_mock),
    )
    monkeypatch.setitem(
        registry_mod.TOOLS_FOR,
        Population.CLIENT,
        (
            registry_mod.TOOLS["whoami"],
            registry_mod.TOOLS["set_availability"],
        ),
    )

    client = ScriptedClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_whoami",
                        "type": "function",
                        "function": {"name": "whoami", "arguments": "{}"},
                    },
                    {
                        "id": "call_avail",
                        "type": "function",
                        "function": {
                            "name": "set_availability",
                            "arguments": '{"available": false, "note": "busy"}',
                        },
                    },
                ],
            },
            {
                "role": "assistant",
                "content": "You are principal_client and marked unavailable.",
            },
        ]
    )

    result = run_tool_loop(
        client,
        [{"role": "user", "content": "who am I and set me unavailable"}],
        population=Population.CLIENT,
        principal=client_principal,
    )

    assert result == "You are principal_client and marked unavailable."
    assert whoami_mock.call_count == 1
    assert availability_mock.call_count == 1
    assert availability_mock.call_args.kwargs["available"] is False
    assert availability_mock.call_args.kwargs["note"] == "busy"
    assert len(client.calls) == 2


def test_fifth_round_raises(client_principal):
    """A fifth model round must raise ToolRoundLimitExceeded."""
    tool_response = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_whoami",
                "type": "function",
                "function": {"name": "whoami", "arguments": "{}"},
            }
        ],
    }
    client = ScriptedClient([dict(tool_response) for _ in range(5)])

    with pytest.raises(ToolRoundLimitExceeded, match="maximum of 4 rounds"):
        run_tool_loop(
            client,
            [{"role": "user", "content": "loop forever"}],
            population=Population.CLIENT,
            principal=client_principal,
        )

    assert len(client.calls) == 4


def test_history_window_keeps_last_12_messages(client_principal):
    """System prompt is prepended; only the last 12 history messages follow."""
    prior = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    client = ScriptedClient([{"role": "assistant", "content": "ok"}])

    run_tool_loop(
        client,
        prior,
        population=Population.CLIENT,
        principal=client_principal,
    )

    sent = client.calls[0]["messages"]
    assert sent[0]["role"] == "system"
    assert sent[0]["content"] == assemble_system_prompt(Population.CLIENT)
    assert len(sent) == 13
    assert sent[1]["content"] == "m8"
    assert sent[-1]["content"] == "m19"


def test_loop_system_prompt_differs_by_population(client_principal):
    """CLIENT and DEV loops inject different system prompts."""
    client = ScriptedClient(
        [
            {"role": "assistant", "content": "client-ok"},
            {"role": "assistant", "content": "dev-ok"},
        ]
    )
    messages = [{"role": "user", "content": "hello"}]

    run_tool_loop(
        client,
        messages,
        population=Population.CLIENT,
        principal=client_principal,
    )
    run_tool_loop(
        client,
        messages,
        population=Population.DEV,
        principal=client_principal,
    )

    client_system = client.calls[0]["messages"][0]["content"]
    dev_system = client.calls[1]["messages"][0]["content"]
    assert client_system == assemble_system_prompt(Population.CLIENT)
    assert dev_system == assemble_system_prompt(Population.DEV)
    assert client_system != dev_system
