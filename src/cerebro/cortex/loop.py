"""Population-gated tool-calling loop for cortex."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

from sqlalchemy.orm import Session

from cerebro.config import settings
from cerebro.cortex.prompts import assemble_system_prompt
from cerebro.db.models import Population, Principal
from cerebro.registry import TOOLS_FOR, ToolSpec

MAX_TOOL_ROUNDS = 4
HISTORY_WINDOW = 12
ToolMode = Literal["native", "json"]

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


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


def _messages_for_model(
    history: list[dict[str, Any]],
    population: Population,
    tool_mode: ToolMode,
) -> list[dict[str, Any]]:
    """Build the model payload: population system prompt plus windowed history."""
    system = {
        "role": "system",
        "content": assemble_system_prompt(population, tool_mode=tool_mode),
    }
    return [system, *_window_history(history)]


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


def _coerce_tool_call(entry: dict[str, Any], index: int) -> dict[str, Any] | None:
    """Normalize a JSON tool entry into OpenAI-shaped tool_call dict."""
    if "function" in entry and isinstance(entry["function"], dict):
        function = entry["function"]
        name = function.get("name")
        if not name:
            return None
        arguments = function.get("arguments", {})
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        return {
            "id": entry.get("id") or f"json_call_{index}",
            "type": "function",
            "function": {"name": name, "arguments": arguments or "{}"},
        }

    name = entry.get("name")
    if not name:
        return None
    arguments = entry.get("arguments", {})
    if isinstance(arguments, dict):
        arguments = json.dumps(arguments)
    return {
        "id": entry.get("id") or f"json_call_{index}",
        "type": "function",
        "function": {"name": name, "arguments": arguments or "{}"},
    }


def _load_json_object(content: str) -> dict[str, Any] | None:
    """Parse a JSON object from raw or fenced assistant content."""
    text = content.strip()
    if not text:
        return None

    candidates = [text]
    fenced = _JSON_FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_json_tool_calls(content: str | None) -> list[dict[str, Any]]:
    """Parse structured JSON tool calls from assistant content."""
    if not content or not isinstance(content, str):
        return []

    payload = _load_json_object(content)
    if payload is None:
        return []

    if "tool_calls" in payload:
        raw_calls = payload["tool_calls"]
        if not isinstance(raw_calls, list):
            return []
        calls: list[dict[str, Any]] = []
        for index, entry in enumerate(raw_calls):
            if not isinstance(entry, dict):
                continue
            coerced = _coerce_tool_call(entry, index)
            if coerced is not None:
                calls.append(coerced)
        return calls

    if "name" in payload:
        coerced = _coerce_tool_call(payload, 0)
        return [coerced] if coerced is not None else []

    return []


def resolve_tool_calls(assistant: dict[str, Any], tool_mode: ToolMode) -> list[dict[str, Any]]:
    """Resolve tool calls for the active mode onto a common dispatch shape."""
    native_calls = list(assistant.get("tool_calls") or [])
    if tool_mode == "native":
        if native_calls:
            return native_calls
        return parse_json_tool_calls(assistant.get("content"))
    return parse_json_tool_calls(assistant.get("content"))


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


def _resolve_tool_mode(tool_mode: ToolMode | None) -> ToolMode:
    """Resolve tool mode from an explicit arg, else settings.tool_mode."""
    if tool_mode is not None:
        return tool_mode
    return settings.tool_mode


def run_tool_loop(
    client: ChatClient,
    messages: list[dict[str, Any]],
    *,
    population: Population,
    principal: Principal,
    session: Session | None = None,
    tool_mode: ToolMode | None = None,
) -> str:
    """Run a capped tool-calling loop against the registry.

    Injects a population-specific system prompt each round, windows history to
    the last 12 non-system messages, caps model rounds at 4, executes every
    resolved tool call in a round, and dispatches through TOOLS_FOR[population].

    tool_mode=native uses API tool_calls and falls back to JSON content parsing
    when tool_calls are absent. tool_mode=json parses structured JSON content only.
    """
    mode = _resolve_tool_mode(tool_mode)
    history = list(messages)
    tools = tool_schemas_for(population)
    request_tools = tools if mode == "native" else None

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        assistant = client.chat(
            _messages_for_model(history, population, mode),
            tools=request_tools,
        )
        if assistant.get("role") is None:
            assistant = {**assistant, "role": "assistant"}
        history.append(assistant)

        tool_calls = resolve_tool_calls(assistant, mode)
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
