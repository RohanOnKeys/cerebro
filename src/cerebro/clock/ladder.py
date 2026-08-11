"""Unacked-task follow-up ladder: pure rung/quiet-hour/rate-cap helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping, Sequence

# Minutes from the rung-0 (initial task card) fire time to each rung, 0..5.
RUNG_MINUTES: tuple[int, ...] = (0, 20, 60, 180, 480, 1440)
MIN_GAP_MINUTES = 20
QUIET_HOUR_START = 22  # UTC, inclusive
QUIET_HOUR_END = 8  # UTC, exclusive


@dataclass(frozen=True)
class LadderView:
    """Lightweight ladder state used by pure functions."""

    rung: int = 0
    last_fired_at: datetime | None = None
    next_due_at: datetime | None = None
    status: str = "active"


@dataclass(frozen=True)
class DueTask:
    """Minimal task view used for coalescing/rate-cap decisions."""

    task_id: str
    number: int
    title: str
    assignee_principal_id: str


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize datetimes to UTC-aware (SQLite often returns naive values)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_quiet_hours(moment: datetime) -> bool:
    """Return True when moment falls in the 22:00-08:00 UTC quiet window."""
    hour = _as_utc(moment).hour
    if QUIET_HOUR_START > QUIET_HOUR_END:
        return hour >= QUIET_HOUR_START or hour < QUIET_HOUR_END
    return QUIET_HOUR_START <= hour < QUIET_HOUR_END


def skip_quiet_hours(moment: datetime) -> datetime:
    """Push a moment forward to QUIET_HOUR_END if it falls inside quiet hours."""
    utc_moment = _as_utc(moment)
    if not is_quiet_hours(utc_moment):
        return utc_moment
    end = utc_moment.replace(hour=QUIET_HOUR_END, minute=0, second=0, microsecond=0)
    if utc_moment.hour >= QUIET_HOUR_START:
        end += timedelta(days=1)
    return end


def due(view: LadderView, *, now: datetime | None = None) -> bool:
    """Return True when the ladder's current rung is due to fire."""
    moment = _as_utc(now) or datetime.now(UTC)
    if view.status != "active":
        return False
    if view.rung >= len(RUNG_MINUTES):
        return False
    if view.rung == 0 and view.last_fired_at is None:
        return True
    next_due_at = _as_utc(view.next_due_at)
    if next_due_at is None:
        return False
    return moment >= next_due_at


def advance(view: LadderView, *, now: datetime | None = None) -> LadderView:
    """Fire the current rung and compute the next one (quiet-hours + min-gap safe)."""
    moment = _as_utc(now) or datetime.now(UTC)
    fired_rung = view.rung
    next_rung = fired_rung + 1
    if next_rung >= len(RUNG_MINUTES):
        return LadderView(
            rung=next_rung, last_fired_at=moment, next_due_at=None, status="exhausted"
        )
    delta_minutes = max(
        MIN_GAP_MINUTES, RUNG_MINUTES[next_rung] - RUNG_MINUTES[fired_rung]
    )
    next_due_at = skip_quiet_hours(moment + timedelta(minutes=delta_minutes))
    return LadderView(
        rung=next_rung, last_fired_at=moment, next_due_at=next_due_at, status="active"
    )


def cancel(view: LadderView) -> LadderView:
    """Cancel remaining rungs (e.g. on ACK)."""
    return LadderView(
        rung=view.rung,
        last_fired_at=view.last_fired_at,
        next_due_at=None,
        status="cancelled",
    )


def group_due_by_assignee(
    due_tasks: Sequence[DueTask],
) -> dict[str, list[DueTask]]:
    """Coalesce multiple due tasks for the same assignee into one group."""
    grouped: dict[str, list[DueTask]] = {}
    for task in due_tasks:
        grouped.setdefault(task.assignee_principal_id, []).append(task)
    return grouped


def allowed_by_rate_cap(
    last_fired_at: datetime | None, *, now: datetime | None = None
) -> bool:
    """Return True when a principal may receive another ladder nudge now.

    Enforces the floor: no principal receives two ladder nudges within
    MIN_GAP_MINUTES, even across different tasks.
    """
    moment = _as_utc(now) or datetime.now(UTC)
    last = _as_utc(last_fired_at)
    if last is None:
        return True
    return moment >= last + timedelta(minutes=MIN_GAP_MINUTES)


def coalesced_body(due_tasks: Sequence[DueTask]) -> str:
    """Build one nudge body listing every coalesced task for a principal."""
    if len(due_tasks) == 1:
        task = due_tasks[0]
        return f"Reminder: task {task.number} ({task.title}) is still unacknowledged."
    listing = ", ".join(f"{task.number} ({task.title})" for task in due_tasks)
    return f"Reminder: {len(due_tasks)} tasks still unacknowledged: {listing}."
