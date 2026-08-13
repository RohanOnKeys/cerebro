"""Phase 8 gate: scripts/seed.py tops up every principal to >= 2 channels."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.seed as seed
from cerebro.db.models import Base, ChannelBinding, Org, Population, Principal


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Org(id="org_1", name="Test Org", created_at=datetime.now(UTC)))
    session.commit()
    yield session
    session.close()


def _principal(db_session, *, id: str) -> Principal:
    principal = Principal(
        id=id, org_id="org_1", population=Population.DEV, created_at=datetime.now(UTC)
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def _binding(db_session, *, principal_id: str, channel: str) -> None:
    db_session.add(
        ChannelBinding(
            id=f"bind_{principal_id}_{channel}",
            principal_id=principal_id,
            channel=channel,
            channel_id=f"real-{channel}",
            verified="verified",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()


def test_plan_bindings_is_pure():
    assert seed.plan_bindings(set()) == ["telegram", "discord"]
    assert seed.plan_bindings({"telegram"}) == ["discord"]
    assert seed.plan_bindings({"telegram", "discord"}) == []
    assert seed.plan_bindings({"telegram", "discord", "slack"}) == []


def test_seed_bindings_tops_up_principal_with_zero_channels(db_session, monkeypatch):
    monkeypatch.setattr(seed, "DRY_RUN", False)
    _principal(db_session, id="p_bare")

    plan = seed.seed_bindings(db_session)

    assert plan == {"p_bare": ["telegram", "discord"]}
    assert seed.existing_channels(db_session, "p_bare") == {"telegram", "discord"}


def test_seed_bindings_leaves_already_covered_principal_alone(db_session, monkeypatch):
    monkeypatch.setattr(seed, "DRY_RUN", False)
    _principal(db_session, id="p_covered")
    _binding(db_session, principal_id="p_covered", channel="slack")
    _binding(db_session, principal_id="p_covered", channel="email")

    plan = seed.seed_bindings(db_session)

    assert plan == {}
    assert seed.existing_channels(db_session, "p_covered") == {"slack", "email"}


def test_seed_bindings_only_adds_the_missing_one(db_session, monkeypatch):
    monkeypatch.setattr(seed, "DRY_RUN", False)
    _principal(db_session, id="p_partial")
    _binding(db_session, principal_id="p_partial", channel="slack")

    plan = seed.seed_bindings(db_session)

    assert plan == {"p_partial": ["telegram"]}
    assert seed.existing_channels(db_session, "p_partial") == {"slack", "telegram"}


def test_dry_run_writes_nothing(db_session, monkeypatch):
    monkeypatch.setattr(seed, "DRY_RUN", True)
    _principal(db_session, id="p_dry")

    plan = seed.seed_bindings(db_session)

    assert plan == {"p_dry": ["telegram", "discord"]}
    assert seed.existing_channels(db_session, "p_dry") == set()


def test_assert_two_channels_each_reports_failures(db_session):
    _principal(db_session, id="p_one_channel")
    _binding(db_session, principal_id="p_one_channel", channel="telegram")
    _principal(db_session, id="p_two_channels")
    _binding(db_session, principal_id="p_two_channels", channel="telegram")
    _binding(db_session, principal_id="p_two_channels", channel="discord")

    failures = seed.assert_two_channels_each(db_session)

    assert failures == [("p_one_channel", 1)]
