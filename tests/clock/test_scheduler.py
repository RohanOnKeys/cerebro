"""Unit tests for the daemon clock scheduler."""

import time
from typing import Any

from cerebro.clock.scheduler import Scheduler


def test_job_fires_while_mocked_listen_handler_responds():
    """A short-interval job can fire while a mocked listen/handler path responds."""
    pulses: list[float] = []
    replies: list[str] = []

    def mock_handler(text: str) -> str:
        return f"ack:{text}"

    scheduler = Scheduler(tick_seconds=0.02)
    scheduler.every(0.05, lambda: pulses.append(time.monotonic()), name="pulse")
    scheduler.start()
    try:
        deadline = time.monotonic() + 0.35
        i = 0
        while time.monotonic() < deadline:
            replies.append(mock_handler(f"msg-{i}"))
            i += 1
            time.sleep(0.02)
    finally:
        scheduler.stop()

    assert len(pulses) >= 2
    assert len(replies) >= 5
    assert all(reply.startswith("ack:") for reply in replies)
    assert scheduler.running is False


def test_run_pending_invokes_due_jobs():
    """run_pending executes due jobs once without starting the thread."""
    hits: list[str] = []
    scheduler = Scheduler()
    scheduler.every(10, lambda: hits.append("a"), name="a")
    ran = scheduler.run_pending()
    assert ran == ["a"]
    assert hits == ["a"]
    assert scheduler.run_pending() == []
