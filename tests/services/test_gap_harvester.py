"""Unit tests for gap harvester pure functions."""

from datetime import UTC, datetime, timedelta

from cerebro.services.gap_harvester import (
    BACKOFF_MINUTES,
    MAX_ASKS,
    ChaseView,
    FieldSpecView,
    harvest_values_from_message,
    missing_fields,
    record_ask,
    should_ask,
    validate_value,
)


def test_missing_fields_lists_required_gaps():
    """Required blank fields are reported as missing."""
    specs = [
        FieldSpecView("email", required=True, validator="email"),
        FieldSpecView("note", required=False, validator="nonempty"),
        FieldSpecView("when", required=True, validator="date"),
    ]
    assert missing_fields({"email": "a@b.co", "when": ""}, specs) == ["when"]


def test_ask_once_until_backoff_elapses():
    """After one ask, should_ask is false until the next backoff window."""
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    chase = ChaseView(field_name="email", ask_count=0)
    assert should_ask(chase, now=now) is True

    after_ask = record_ask(chase, asked_at=now)
    assert after_ask.ask_count == 1
    assert after_ask.next_ask_at == now + timedelta(minutes=BACKOFF_MINUTES[1])
    assert should_ask(after_ask, now=now) is False
    assert should_ask(after_ask, now=now + timedelta(minutes=BACKOFF_MINUTES[1] - 1)) is False
    assert should_ask(after_ask, now=now + timedelta(minutes=BACKOFF_MINUTES[1])) is True


def test_backoff_exhausts_after_four_asks():
    """A chase becomes exhausted after the fourth ask."""
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    chase = ChaseView(field_name="email", ask_count=0)
    for _ in range(MAX_ASKS):
        assert should_ask(chase, now=now) is True
        chase = record_ask(chase, asked_at=now)
        now = chase.next_ask_at or (now + timedelta(days=3))

    assert chase.ask_count == MAX_ASKS
    assert chase.status == "exhausted"
    assert should_ask(chase, now=now) is False


def test_value_in_unrelated_message_closes_chase():
    """A value embedded in an unrelated message closes the matching chase."""
    specs = [FieldSpecView("email", required=True, validator="email")]
    chases = [ChaseView(field_name="email", ask_count=1)]
    text = "not sure about thursday, weather looks rough — email me at alice@example.com thanks"

    closed = harvest_values_from_message(text, chases, specs)

    assert closed == [("email", "alice@example.com")]
    assert validate_value("email", "alice@example.com") is True
