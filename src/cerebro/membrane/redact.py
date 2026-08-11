"""Redaction: strip policy-denied fields from structured data or digest text."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

# Three audience buckets for a digest fan-out. Mirrors the strictest seeded
# policy per target (dev/client) plus a middle "team" tier for ops/lead, who
# see less than dev but more than an external client.
DIGEST_VARIANT_HIDDEN_FIELDS: dict[str, frozenset[str]] = {
    "client": frozenset({"stack_trace", "estimate", "risk"}),
    "team": frozenset({"stack_trace"}),
    "dev": frozenset(),
}

_LABELED_LINE_RE = re.compile(r"^\s*(\w+)\s*:", re.I)


def redact_fields(fields: Mapping[str, Any], hidden: Sequence[str]) -> dict[str, Any]:
    """Return fields with every key in hidden removed."""
    hidden_lower = {name.lower() for name in hidden}
    return {key: value for key, value in fields.items() if key.lower() not in hidden_lower}


def redact_digest_text(text: str, hidden_fields: Sequence[str]) -> str:
    """Strip 'field: value' labeled lines whose label is in hidden_fields."""
    hidden_lower = {name.lower() for name in hidden_fields}
    if not hidden_lower:
        return text
    kept_lines = []
    for line in text.splitlines():
        match = _LABELED_LINE_RE.match(line)
        if match and match.group(1).lower() in hidden_lower:
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def build_digest_variants(text: str) -> dict[str, str]:
    """Build client/team/dev redacted variants of one digest."""
    return {
        variant: redact_digest_text(text, hidden)
        for variant, hidden in DIGEST_VARIANT_HIDDEN_FIELDS.items()
    }
