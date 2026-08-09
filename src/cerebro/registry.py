"""Tool registry with population-gated tool access."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Population, Principal
from cerebro.ingress.enrollment import enroll_unknown_sender

# Internal populations that may run team/ops tools. CLIENT is excluded.
_TEAM_POPULATIONS = frozenset(
    {
        Population.OPS,
        Population.DEV,
        Population.LEAD,
        Population.ADMIN,
    }
)
_ALL_POPULATIONS = frozenset(Population)


@dataclass(frozen=True)
class ToolSpec:
    """Specification for a registered tool.

    Attributes:
        name: Stable tool identifier.
        description: Human-readable summary for callers/LLMs.
        parameters: JSON-Schema-like parameter object.
        handler: Callable that executes the tool.
        allowed_populations: Populations permitted to see/invoke this tool.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    allowed_populations: frozenset[Population]


def whoami(*, principal: Principal, **_: Any) -> dict[str, str]:
    """Return the caller's principal identity."""
    return {
        "principal_id": principal.id,
        "org_id": principal.org_id,
        "population": principal.population.value,
        "email": principal.email or "",
    }


def enroll_principal(
    *,
    session: Session,
    org_id: str,
    channel: str,
    channel_id: str,
    conversation_id: str,
    **_: Any,
) -> dict[str, str]:
    """Enroll an unknown sender via the existing enrollment service.

    Creates a CLIENT principal and pending channel binding. Restricted to
    team/ops populations in the registry (not CLIENT self-service).
    """
    principal, binding = enroll_unknown_sender(
        session, org_id, channel, channel_id, conversation_id
    )
    return {
        "principal_id": principal.id,
        "binding_id": binding.id,
        "population": principal.population.value,
        "verified": binding.verified,
    }


def set_availability(
    *,
    principal: Principal,
    available: bool,
    note: str = "",
    **_: Any,
) -> dict[str, Any]:
    """Record availability for the calling principal.

    Thin Phase 2.1 handler: persists no ledger yet; returns a structured ack
    so cortex can call a real tool later without inventing a parallel identity
    system.
    """
    return {
        "principal_id": principal.id,
        "available": available,
        "note": note,
        "status": "recorded",
    }


TOOLS: dict[str, ToolSpec] = {
    "whoami": ToolSpec(
        name="whoami",
        description="Return the caller's principal id, org, and population.",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=whoami,
        allowed_populations=_ALL_POPULATIONS,
    ),
    "enroll_principal": ToolSpec(
        name="enroll_principal",
        description="Enroll an unknown sender as a CLIENT principal with a pending binding.",
        parameters={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "channel": {"type": "string"},
                "channel_id": {"type": "string"},
                "conversation_id": {"type": "string"},
            },
            "required": ["org_id", "channel", "channel_id", "conversation_id"],
            "additionalProperties": False,
        },
        handler=enroll_principal,
        # Ops/team only: CLIENT must not enroll other principals.
        allowed_populations=_TEAM_POPULATIONS,
    ),
    "set_availability": ToolSpec(
        name="set_availability",
        description="Record whether the calling principal is currently available.",
        parameters={
            "type": "object",
            "properties": {
                "available": {"type": "boolean"},
                "note": {"type": "string"},
            },
            "required": ["available"],
            "additionalProperties": False,
        },
        handler=set_availability,
        allowed_populations=_ALL_POPULATIONS,
    ),
}


def _build_tools_for() -> dict[Population, tuple[ToolSpec, ...]]:
    """Build the population → allowed tools index."""
    return {
        population: tuple(
            tool for tool in TOOLS.values() if population in tool.allowed_populations
        )
        for population in Population
    }


TOOLS_FOR: Mapping[Population, tuple[ToolSpec, ...]] = _build_tools_for()


def tools_for(population: Population) -> tuple[ToolSpec, ...]:
    """Return tools allowed for the given population."""
    return TOOLS_FOR[population]
