"""Population-gated tool-calling loop for cortex."""

from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy.orm import Session

from cerebro.db.models import Population, Principal
from cerebro.registry import TOOLS_FOR, ToolSpec

MAX_TOOL_ROUNDS = 4
HISTORY_WINDOW = 12


class ToolRoundLimitExceeded(RuntimeError):
    """Raised when the loop would start a round beyond MAX_TOOL_ROUNDS."""


class ChatClient(Protocol):
    """Minimal chat client protocol used by the tool loop."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return an assistant message dict (content and/or tool_calls)."""


def tool_schemas_for(population: Population) -> list[dict[str, Any]]:
    """Build OpenAI-compatible tool schemas for a population."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in TOOLS_FOR[population]
    ]


def _allowed_tools(population: Population) -> dict[str, ToolSpec]:
    """Index allowed tools by name for a population."""
    return {tool.name: tool for tool in TOOLS_FOR[population]}


def _window_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the last HISTORY_WINDOW turns/messages."""
    if len(messages) <= HISTORY_WINDOW:
        return list(messages)
    return list(messages[-HISTORY_WINDOW:])


def _parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse tool call arguments from JSON string or dict."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def execute_tool_call(
    tool_call: dict[str, Any],
    *,
    population: Population,
    principal: Principal,
    session: Session | None = None,
) -> dict[str, Any]:
    """Dispatch one tool call through the population-gated registry."""
    function = tool_call.get("function") or {}
    name = function.get("name") or ""
    allowed = _allowed_tools(population)
    tool = allowed.get(name)
    if tool is None:
        return {
            "error": "tool_not_allowed",
            "tool": name,
            "population": population.value,
        }

    args = _parse_arguments(function.get("arguments"))
    result = tool.handler(
        **args,
        principal=principal,
        session=session,
    )
    if isinstance(result, dict):
        return result
    return {"result": result}


def run_tool_loop(
    client: ChatClient,
    messages: list[dict[str, Any]],
    *,
    population: Population,
    principal: Principal,
    session: Session | None = None,
) -> str:
    """Run a capped tool-calling loop against the registry.

    Behavior:
    - History sent to the model is truncated to the last 12 messages.
    - At most 4 model rounds; attempting a 5th raises ToolRoundLimitExceeded.
    - Every tool_call in a model response is executed in that round.
    - Tools are taken from TOOLS_FOR[population] for schemas and dispatch.
    """
    history = list(messages)
    tools = tool_schemas_for(population)

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        assistant = client.chat(_window_history(history), tools=tools)
        if assistant.get("role") is None:
            assistant = {**assistant, "role": "assistant"}
        history.append(assistant)

        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            content = assistant.get("content")
            return content if isinstance(content, str) else (content or "")

        for tool_call in tool_calls:
            result = execute_tool_call(
                tool_call,
                population=population,
                principal=principal,
                session=session,
            )
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(result),
                }
            )

    raise ToolRoundLimitExceeded(
        f"Tool-calling loop exceeded maximum of {MAX_TOOL_ROUNDS} rounds"
    )
