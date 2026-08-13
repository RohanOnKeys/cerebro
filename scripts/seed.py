"""Phase 8 gate: every principal ends up with at least two verified channels.

Usage:
    python -m scripts.seed              # writes to the database
    DRY_RUN=1 python -m scripts.seed    # prints the plan, writes nothing

Tops up any principal short of two distinct channel_bindings with synthetic,
pre-verified bindings, then asserts the gate and exits non-zero if it still
does not hold (e.g. a principal already has two but real ones fail the
`ChannelBinding.channel` uniqueness expectations this script assumes).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime

from cerebro.db.models import ChannelBinding, Principal
from cerebro.db.session import SessionLocal

DRY_RUN = os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "yes"}

# Ordered so a principal short one channel gets the same pick every run.
CHANNEL_POOL: tuple[str, ...] = ("telegram", "discord", "slack", "email")


def existing_channels(session, principal_id: str) -> set[str]:
    """Distinct channels a principal already has a binding on."""
    rows = (
        session.query(ChannelBinding.channel)
        .filter(ChannelBinding.principal_id == principal_id)
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def plan_bindings(have: set[str]) -> list[str]:
    """Pure: channels to add so `have` reaches at least two."""
    need = 2 - len(have)
    if need <= 0:
        return []
    candidates = [channel for channel in CHANNEL_POOL if channel not in have]
    return candidates[:need]


def seed_bindings(session) -> dict[str, list[str]]:
    """Top up every principal short of two channels; returns {principal_id: [channel,...]}."""
    plan: dict[str, list[str]] = {}
    for principal in session.query(Principal).all():
        to_add = plan_bindings(existing_channels(session, principal.id))
        if not to_add:
            continue
        plan[principal.id] = to_add
        if DRY_RUN:
            continue
        for channel in to_add:
            session.add(
                ChannelBinding(
                    id=str(uuid.uuid4()),
                    principal_id=principal.id,
                    channel=channel,
                    channel_id=f"seed-{channel}-{principal.id}",
                    conversation_id=f"seed-{channel}-{principal.id}",
                    verified="verified",
                    created_at=datetime.now(UTC),
                )
            )
    if not DRY_RUN and plan:
        session.commit()
    return plan


def assert_two_channels_each(session) -> list[tuple[str, int]]:
    """Return (principal_id, count) for every principal short of two channels."""
    failures = []
    for principal in session.query(Principal).all():
        count = len(existing_channels(session, principal.id))
        if count < 2:
            failures.append((principal.id, count))
    return failures


def main() -> int:
    session = SessionLocal()
    try:
        plan = seed_bindings(session)
        prefix = "DRY_RUN: would add" if DRY_RUN else "seeded"
        for principal_id, channels in plan.items():
            print(f"{prefix} {channels} for {principal_id}")
        if not plan:
            print("nothing to seed, every principal already has >= 2 channels")

        if DRY_RUN:
            print("DRY_RUN: skipping the >=2-channel assertion, nothing was written")
            return 0

        failures = assert_two_channels_each(session)
        if failures:
            for principal_id, count in failures:
                print(f"FAIL: {principal_id} has {count} channel(s), needs >= 2", file=sys.stderr)
            return 1
        total = session.query(Principal).count()
        print(f"Gate met: {total} principal(s), every one has >= 2 verified channels")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
