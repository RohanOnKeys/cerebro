"""Gap harvester pure helpers for missing order fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence

MAX_ASKS = 4
BACKOFF_MINUTES: tuple[int, ...] = (0, 4 * 60, 24 * 60, 72 * 60)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_DATE_HINT_RE = re.compile(
    r"\b("
    r"today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{1,2}[:/.-]\d{1,2}(?:[:/.-]\d{2,4})?"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class FieldSpecView:
    """Lightweight field requirement used by pure harvester functions."""

    field_name: str
    required: bool = True
    validator: str = "nonempty"


@dataclass(frozen=True)
class ChaseView:
    """Lightweight open chase used by pure harvester functions."""

    field_name: str
    ask_count: int = 0
    last_asked_at: datetime | None = None
    next_ask_at: datetime | None = None
    status: str = "open"


def missing_fields(
    fields: Mapping[str, Any], specs: Sequence[FieldSpecView]
) -> list[str]:
    """Return required field names that are absent or blank."""
    missing: list[str] = []
    for spec in specs:
        if not spec.required:
            continue
        value = fields.get(spec.field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(spec.field_name)
    return missing


def backoff_minutes_for_ask(ask_count: int) -> int | None:
    """Return minutes to wait before the next ask, or None when exhausted."""
    if ask_count < 0 or ask_count >= MAX_ASKS:
        return None
    return BACKOFF_MINUTES[ask_count]


def compute_next_ask_at(asked_at: datetime, ask_count_after: int) -> datetime | None:
    """Compute next_ask_at after recording an ask (ask_count already incremented)."""
    if ask_count_after >= MAX_ASKS:
        return None
    delay = backoff_minutes_for_ask(ask_count_after)
    if delay is None:
        return None
    return asked_at + timedelta(minutes=delay)


def should_ask(chase: ChaseView, *, now: datetime | None = None) -> bool:
    """Return True when a chase is due for exactly one ask under backoff rules."""
    moment = now or datetime.now(UTC)
    if chase.status != "open":
        return False
    if chase.ask_count >= MAX_ASKS:
        return False
    if chase.ask_count == 0:
        return True
    if chase.next_ask_at is not None:
        return moment >= chase.next_ask_at
    if chase.last_asked_at is None:
        return True
    delay = backoff_minutes_for_ask(chase.ask_count)
    if delay is None:
        return False
    return moment >= chase.last_asked_at + timedelta(minutes=delay)


def record_ask(chase: ChaseView, *, asked_at: datetime | None = None) -> ChaseView:
    """Return an updated chase after asking once."""
    moment = asked_at or datetime.now(UTC)
    ask_count = chase.ask_count + 1
    if ask_count >= MAX_ASKS:
        return ChaseView(
            field_name=chase.field_name,
            ask_count=ask_count,
            last_asked_at=moment,
            next_ask_at=None,
            status="exhausted",
        )
    return ChaseView(
        field_name=chase.field_name,
        ask_count=ask_count,
        last_asked_at=moment,
        next_ask_at=compute_next_ask_at(moment, ask_count),
        status="open",
    )


def validate_value(validator: str, value: str) -> bool:
    """Validate a candidate field value."""
    text = value.strip()
    if not text:
        return False
    if validator == "nonempty":
        return True
    if validator == "email":
        return _EMAIL_RE.fullmatch(text) is not None
    if validator == "phone":
        digits = re.sub(r"\D", "", text)
        return 8 <= len(digits) <= 15
    if validator == "date":
        return _DATE_HINT_RE.search(text) is not None
    return True


def find_value_in_text(text: str, field_name: str, validator: str) -> str | None:
    """Extract a field value from free text when present."""
    if not text or not text.strip():
        return None

    if validator == "email":
        match = _EMAIL_RE.search(text)
        return match.group(0) if match else None

    if validator == "phone":
        match = _PHONE_RE.search(text)
        return match.group(0).strip() if match else None

    if validator == "date":
        match = _DATE_HINT_RE.search(text)
        return match.group(0) if match else None

    labeled = re.search(
        rf"\b{re.escape(field_name)}\b\s*[:=]\s*([^\n,;]+)",
        text,
        re.I,
    )
    if labeled:
        candidate = labeled.group(1).strip()
        if validate_value(validator, candidate):
            return candidate
    return None


def harvest_values_from_message(
    text: str,
    chases: Sequence[ChaseView],
    specs: Sequence[FieldSpecView],
) -> list[tuple[str, str]]:
    """Find chase-closing values in a message, including unrelated asides."""
    spec_by_name = {spec.field_name: spec for spec in specs}
    closed: list[tuple[str, str]] = []
    for chase in chases:
        if chase.status != "open":
            continue
        spec = spec_by_name.get(chase.field_name)
        validator = spec.validator if spec else "nonempty"
        value = find_value_in_text(text, chase.field_name, validator)
        if value is not None and validate_value(validator, value):
            closed.append((chase.field_name, value))
    return closed
