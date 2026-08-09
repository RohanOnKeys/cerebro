"""Daemon-thread interval scheduler for background jobs."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ScheduledJob:
    """A named interval job."""

    name: str
    interval_seconds: float
    callback: Callable[[], Any]
    next_run_at: float


class Scheduler:
    """Minimal daemon-thread scheduler that ticks interval jobs."""

    def __init__(self, *, tick_seconds: float = 0.05) -> None:
        self._tick_seconds = max(0.01, tick_seconds)
        self._jobs: list[ScheduledJob] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def every(
        self,
        interval_seconds: float,
        callback: Callable[[], Any],
        *,
        name: str | None = None,
    ) -> str:
        """Register a job to run about every interval_seconds."""
        job_name = name or getattr(callback, "__name__", "job")
        now = time.monotonic()
        with self._lock:
            self._jobs.append(
                ScheduledJob(
                    name=job_name,
                    interval_seconds=max(0.001, float(interval_seconds)),
                    callback=callback,
                    next_run_at=now,
                )
            )
        return job_name

    def start(self) -> None:
        """Start the daemon scheduler thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="cerebro-clock",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        """Signal the scheduler to stop and join the thread."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    @property
    def running(self) -> bool:
        """Return True when the daemon thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def run_pending(self, *, now: float | None = None) -> list[str]:
        """Run all jobs that are due once (useful for tests)."""
        moment = time.monotonic() if now is None else now
        ran: list[str] = []
        with self._lock:
            jobs = list(self._jobs)
        for job in jobs:
            if moment >= job.next_run_at:
                job.callback()
                job.next_run_at = moment + job.interval_seconds
                ran.append(job.name)
        return ran

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            self.run_pending()
            self._stop.wait(self._tick_seconds)
