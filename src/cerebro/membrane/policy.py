"""Crossing policy lookup: what happens when content moves source -> target.

Fail-closed by design: a (source, target) pair with no seeded row is DENY,
not ALLOW. The six seed rows (migration 0009) are the only crossings
permitted or redacted out of the box; anything else needs a new row.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Policy, PolicyAction, Population

# Mirrors migration 0009's seed data. Migrations stay self-contained (they
# don't import this), but tests and any repair/reseed tooling use this as
# the single source of truth instead of re-typing the six rows.
DEFAULT_POLICIES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("dev", "client", PolicyAction.REDACT.value, ("stack_trace", "estimate")),
    ("ops", "client", PolicyAction.REDACT.value, ("estimate",)),
    ("lead", "client", PolicyAction.REDACT.value, ("estimate", "risk")),
    ("admin", "client", PolicyAction.DENY.value, ()),
    ("client", "dev", PolicyAction.ALLOW.value, ()),
    ("client", "ops", PolicyAction.ALLOW.value, ()),
)


def _population_value(population: Population | str) -> str:
    return population.value if hasattr(population, "value") else population


def loads_redact_fields(raw: str | None) -> list[str]:
    """Parse a redact_fields_json payload into a list."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return list(data) if isinstance(data, list) else []


@dataclass(frozen=True)
class PolicyDecision:
    """Resolved outcome for one crossing attempt."""

    action: str
    redact_fields: tuple[str, ...] = ()


_DEFAULT_DENY = PolicyDecision(action=PolicyAction.DENY.value, redact_fields=())


def get_policy_row(
    session: Session, *, source: Population | str, target: Population | str
) -> Policy | None:
    """Fetch the seeded policy row for a (source, target) pair, if any."""
    return (
        session.query(Policy)
        .filter(
            Policy.source_population == _population_value(source),
            Policy.target_population == _population_value(target),
        )
        .first()
    )


def evaluate_crossing(
    session: Session, *, source: Population | str, target: Population | str
) -> PolicyDecision:
    """Resolve the policy decision for one crossing; unlisted pairs deny."""
    row = get_policy_row(session, source=source, target=target)
    if row is None:
        return _DEFAULT_DENY
    return PolicyDecision(
        action=row.action, redact_fields=tuple(loads_redact_fields(row.redact_fields_json))
    )


def serialize_policy(policy: Policy) -> dict[str, Any]:
    """Serialize a Policy row for tool/API responses."""
    return {
        "id": policy.id,
        "source_population": policy.source_population,
        "target_population": policy.target_population,
        "action": policy.action,
        "redact_fields": loads_redact_fields(policy.redact_fields_json),
    }


def list_policies(session: Session) -> list[Policy]:
    """List every seeded policy row."""
    return session.query(Policy).order_by(Policy.source_population, Policy.target_population).all()


def seed_default_policies(session: Session) -> list[Policy]:
    """Insert DEFAULT_POLICIES; no-op if the table is already populated."""
    if session.query(Policy).count() > 0:
        return list_policies(session)
    now = datetime.now(UTC)
    rows = [
        Policy(
            id=str(uuid.uuid4()),
            source_population=source,
            target_population=target,
            action=action,
            redact_fields_json=json.dumps(list(redact_fields)),
            created_at=now,
        )
        for source, target, action, redact_fields in DEFAULT_POLICIES
    ]
    session.add_all(rows)
    session.commit()
    return rows
