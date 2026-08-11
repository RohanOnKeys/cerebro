"""Population-aware cortex prompt assembly."""

from __future__ import annotations

import json
from typing import Literal

from cerebro.db.models import Population
from cerebro.registry import TOOLS, TOOLS_FOR

ToolMode = Literal["native", "json"]

_BEHAVIOR: dict[Population, str] = {
    Population.CLIENT: (
        "You are Cerebro speaking with an external client. "
        "Be clear, concise, and non-technical unless asked. "
        "Do not discuss internal runbooks, CI controls, enrollment of other principals, "
        "or staff-only operational detail."
    ),
    Population.OPS: (
        "You are Cerebro assisting operations staff. "
        "Prioritise reliable execution, status clarity, and safe tool use. "
        "Surface blockers early and keep replies actionable."
    ),
    Population.DEV: (
        "You are Cerebro assisting a developer. "
        "Prefer precise technical language, explicit assumptions, and tool-backed answers. "
        "You may discuss internals, enrollment flows, and engineering context relevant to the request."
    ),
    Population.LEAD: (
        "You are Cerebro assisting a team lead. "
        "Balance operational clarity with enough technical detail to support decisions. "
        "Call out risks, ownership, and next actions."
    ),
    Population.ADMIN: (
        "You are Cerebro assisting an administrator. "
        "You may reason about identity, enrollment, and cross-population policy. "
        "Prefer least privilege and auditability when recommending actions."
    ),
}

# Population-specific notes layered onto the dynamically computed allowed/denied
# tool lists below. Keep these about *judgment*, not tool names — the tool
# names are derived from the registry so this can never drift out of sync
# with it again (it previously hardcoded a 3-tool list from Phase 2 and
# silently went stale as Phase 3/4 added 13 more tools).
_POLICY_NOTES: dict[Population, str] = {
    Population.CLIENT: (
        "Never invent elevated access. If a request needs a denied tool, refuse and explain the limit."
    ),
    Population.OPS: (
        "Use enroll_principal only when onboarding a sender is explicitly required. "
        "Do not expose client PII beyond what the tools return."
    ),
    Population.DEV: (
        "Prefer tool calls over speculation for identity, order, task, and meeting questions. "
        "Inspect state via whoami/list_* before mutating it."
    ),
    Population.LEAD: (
        "Escalate ambiguity rather than guessing policy exceptions. "
        "Keep decisions attributable to tool results."
    ),
    Population.ADMIN: (
        "You may authorize enrollment, task, and meeting changes when requested. "
        "Refuse any action outside the registered tool surface."
    ),
}


def behavior_prompt(population: Population) -> str:
    """Return the behavior instructions for a population."""
    return _BEHAVIOR[population]


def policy_prompt(population: Population) -> str:
    """Return the tool and access policy for a population, computed from the registry."""
    allowed = sorted(tool.name for tool in TOOLS_FOR[population])
    denied = sorted(name for name in TOOLS if name not in allowed)

    lines = [
        f"Policy: population={population.value}.",
        f"Allowed tools: {', '.join(allowed)}.",
    ]
    if denied:
        lines.append(f"Denied tools: {', '.join(denied)}.")
    note = _POLICY_NOTES.get(population)
    if note:
        lines.append(note)
    return " ".join(lines)


def json_tool_mode_prompt(population: Population) -> str:
    """Return JSON tool-calling instructions for models without native tools."""
    catalog = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in TOOLS_FOR[population]
    ]
    return (
        "TOOL_MODE=json. "
        "When you need a tool, reply with JSON only in this shape: "
        '{"tool_calls":[{"name":"<tool_name>","arguments":{...}}]}. '
        "When you are done, reply with plain natural language (not JSON). "
        f"Available tools: {json.dumps(catalog)}"
    )


def assemble_system_prompt(
    population: Population, *, tool_mode: ToolMode = "native"
) -> str:
    """Assemble the full system prompt for a population and tool mode."""
    prompt = f"{behavior_prompt(population)}\n\n{policy_prompt(population)}"
    if tool_mode == "json":
        return f"{prompt}\n\n{json_tool_mode_prompt(population)}"
    return prompt
