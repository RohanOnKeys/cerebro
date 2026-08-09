"""Unit tests for native vs JSON tool modes."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import cerebro.registry as registry_mod
from cerebro.cortex.loop import parse_json_tool_calls, resolve_tool_calls, run_tool_loop
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


def _patch_whoami(monkeypatch: pytest.MonkeyPatch, handler: MagicMock) -> None:
    monkeypatch.setitem(
        registry_mod.TOOLS,
        "whoami",
        replace(registry_mod.TOOLS["whoami"], handler=handler),
    )
    monkeypatch.setitem(
        registry_mod.TOOLS_FOR,
        Population.CLIENT,
        (
            registry_mod.TOOLS["whoami"],
            registry_mod.TOOLS["set_availability"],
        ),
    )


def test_native_and_json_modes_dispatch_same_tool(client_principal, monkeypatch):
    """Same conversation yields the same whoami dispatch under both modes."""
    whoami_mock = MagicMock(
        side_effect=lambda **kwargs: {
            "principal_id": kwargs["principal"].id,
            "population": kwargs["principal"].population.value,
            "org_id": kwargs["principal"].org_id,
            "email": kwargs["principal"].email or "",
        }
    )
    _patch_whoami(monkeypatch, whoami_mock)

    conversation = [{"role": "user", "content": "who am I?"}]

    native_client = ScriptedClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_whoami",
                        "type": "function",
                        "function": {"name": "whoami", "arguments": "{}"},
                    }
                ],
            },
            {"role": "assistant", "content": "You are principal_client."},
        ]
    )
    json_client = ScriptedClient(
        [
            {
                "role": "assistant",
                "content": json.dumps(
                    {"tool_calls": [{"name": "whoami", "arguments": {}}]}
                ),
            },
            {"role": "assistant", "content": "You are principal_client."},
        ]
    )

    native_result = run_tool_loop(
        native_client,
        conversation,
        population=Population.CLIENT,
        principal=client_principal,
        tool_mode="native",
    )
    json_result = run_tool_loop(
        json_client,
        conversation,
        population=Population.CLIENT,
        principal=client_principal,
        tool_mode="json",
    )

    assert native_result == json_result == "You are principal_client."
    assert whoami_mock.call_count == 2
    native_kwargs = whoami_mock.call_args_list[0].kwargs
    json_kwargs = whoami_mock.call_args_list[1].kwargs
    assert native_kwargs["principal"].id == json_kwargs["principal"].id
    assert native_client.calls[0]["tools"] is not None
    assert json_client.calls[0]["tools"] is None


def test_native_falls_back_to_json_content_when_tool_calls_missing(
    client_principal, monkeypatch
):
    """Native mode parses JSON content when tool_calls are unavailable."""
    whoami_mock = MagicMock(
        return_value={
            "principal_id": "principal_client",
            "population": "client",
            "org_id": "org_1",
            "email": "client@test.com",
        }
    )
    _patch_whoami(monkeypatch, whoami_mock)

    client = ScriptedClient(
        [
            {
                "role": "assistant",
                "content": json.dumps(
                    {"tool_calls": [{"name": "whoami", "arguments": {}}]}
                ),
            },
            {"role": "assistant", "content": "done"},
        ]
    )

    result = run_tool_loop(
        client,
        [{"role": "user", "content": "who am I?"}],
        population=Population.CLIENT,
        principal=client_principal,
        tool_mode="native",
    )

    assert result == "done"
    assert whoami_mock.call_count == 1


def test_parse_json_tool_calls_supports_fenced_payload():
    """Fenced JSON tool payloads normalize to OpenAI-shaped tool_calls."""
    content = """```json
{"tool_calls":[{"name":"set_availability","arguments":{"available":true}}]}
```"""
    calls = parse_json_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "set_availability"
    assert json.loads(calls[0]["function"]["arguments"]) == {"available": True}


def test_resolve_tool_calls_json_mode_ignores_native_field():
    """JSON mode uses content parsing even if tool_calls is present."""
    assistant = {
        "content": json.dumps({"tool_calls": [{"name": "whoami", "arguments": {}}]}),
        "tool_calls": [
            {
                "id": "ignored",
                "type": "function",
                "function": {"name": "set_availability", "arguments": "{}"},
            }
        ],
    }
    calls = resolve_tool_calls(assistant, "json")
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "whoami"


def test_json_mode_system_prompt_includes_tool_catalog():
    """JSON mode system prompts include TOOL_MODE instructions and tool names."""
    prompt = assemble_system_prompt(Population.CLIENT, tool_mode="json")
    assert "TOOL_MODE=json" in prompt
    assert "whoami" in prompt
    assert "set_availability" in prompt
    assert assemble_system_prompt(Population.CLIENT, tool_mode="native") != prompt
