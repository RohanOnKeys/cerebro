"""Frozen-clock unit tests for the unacked-task ladder, one rule at a time."""

from datetime import UTC, datetime, timedelta

from cerebro.clock.ladder import (
    MIN_GAP_MINUTES,
    RUNG_MINUTES,
    DueTask,
    LadderView,
    advance,
    allowed_by_rate_cap,
    cancel,
    coalesced_body,
    due,
    group_due_by_assignee,
    is_quiet_hours,
    skip_quiet_hours,
)

NOON = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def test_rung_zero_due_immediately_on_a_fresh_ladder():
    assert due(LadderView(), now=NOON) is True


def test_advance_progresses_through_all_six_rungs_then_exhausts():
    view = LadderView()
    for expected_rung in range(1, len(RUNG_MINUTES)):
        view = advance(view, now=NOON)
        assert view.rung == expected_rung
        assert view.status == "active"
    exhausted = advance(view, now=NOON)
    assert exhausted.status == "exhausted"
    assert due(exhausted, now=NOON + timedelta(days=10)) is False


def test_two_rungs_never_fire_within_twenty_minutes():
    view = advance(LadderView(), now=NOON)
    assert view.next_due_at is not None
    assert view.next_due_at >= NOON + timedelta(minutes=MIN_GAP_MINUTES)
    # Not due one minute before the gap elapses.
    assert due(view, now=NOON + timedelta(minutes=MIN_GAP_MINUTES - 1)) is False
    assert due(view, now=view.next_due_at) is True


def test_quiet_hours_window_is_22_to_8_utc():
    assert is_quiet_hours(datetime(2026, 8, 11, 23, 0, tzinfo=UTC)) is True
    assert is_quiet_hours(datetime(2026, 8, 12, 3, 0, tzinfo=UTC)) is True
    assert is_quiet_hours(datetime(2026, 8, 11, 12, 0, tzinfo=UTC)) is False


def test_skip_quiet_hours_pushes_to_next_morning():
    late_night = datetime(2026, 8, 11, 23, 30, tzinfo=UTC)
    pushed = skip_quiet_hours(late_night)
    assert pushed == datetime(2026, 8, 12, 8, 0, tzinfo=UTC)


def test_advance_into_quiet_hours_is_pushed_past_it():
    # rung 3 -> rung 4 is a +300 minute jump; land it inside quiet hours.
    late = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)
    view = LadderView(rung=3, status="active")
    advanced = advance(view, now=late)
    assert is_quiet_hours(advanced.next_due_at) is False


def test_ack_cancels_remaining_rungs():
    view = advance(LadderView(), now=NOON)
    cancelled = cancel(view)
    assert cancelled.status == "cancelled"
    assert cancelled.next_due_at is None
    assert due(cancelled, now=NOON + timedelta(days=1)) is False


def test_coalescing_groups_due_tasks_by_assignee():
    tasks = [
        DueTask("t1", 1, "a", "p1"),
        DueTask("t2", 2, "b", "p1"),
        DueTask("t3", 3, "c", "p2"),
    ]
    grouped = group_due_by_assignee(tasks)
    assert set(grouped.keys()) == {"p1", "p2"}
    assert len(grouped["p1"]) == 2
    assert len(grouped["p2"]) == 1


def test_coalesced_body_lists_every_task_once_grouped():
    tasks = [DueTask("t1", 1, "a", "p1"), DueTask("t2", 2, "b", "p1")]
    body = coalesced_body(tasks)
    assert "1 (a)" in body
    assert "2 (b)" in body


def test_rate_cap_blocks_a_second_nudge_within_the_gap():
    last_fired = NOON
    assert allowed_by_rate_cap(last_fired, now=NOON + timedelta(minutes=5)) is False
    assert (
        allowed_by_rate_cap(last_fired, now=NOON + timedelta(minutes=MIN_GAP_MINUTES))
        is True
    )


def test_rate_cap_allows_first_nudge_when_never_fired():
    assert allowed_by_rate_cap(None, now=NOON) is True
