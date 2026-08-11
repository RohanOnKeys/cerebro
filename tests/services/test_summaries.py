"""Unit tests for summary request/chase/merge and action-item -> task spawning."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro import config as config_module
from cerebro.db.models import Base, NudgeKind, Org, Population, Principal, Task
from cerebro.services.nudges import list_nudges
from cerebro.services.summaries import (
    extract_action_items,
    process_due_summary_chases,
    process_due_summary_merges,
    request_summary,
    submit_summary_entry,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def org(db_session):
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


@pytest.fixture
def requester(db_session, org):
    principal = Principal(
        id="p_requester",
        org_id=org.id,
        population=Population.LEAD,
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def test_extract_action_items_matches_bullets_and_todo_labels():
    text = "\n".join(
        [
            "notes about the sprint",
            "- ship the release notes",
            "* fix the flaky test",
            "TODO: rotate the API key",
            "not an action item",
        ]
    )
    items = extract_action_items(text)
    assert items == ["ship the release notes", "fix the flaky test", "rotate the API key"]


def test_request_summary_creates_order_and_notifies_requester(db_session, org, requester):
    order = request_summary(db_session, principal=requester, topic="sprint retro")

    assert order.order_type == "summary"
    nudges = list_nudges(db_session, kind=NudgeKind.SUMMARY_REQUEST.value)
    assert len(nudges) == 1
    assert nudges[0].principal_id == requester.id


def test_two_dumps_merge_into_one_digest(db_session, org, requester):
    order = request_summary(db_session, principal=requester, topic="sprint retro")
    submit_summary_entry(db_session, order_id=order.id, principal_id="p_a", text="went well")
    submit_summary_entry(db_session, order_id=order.id, principal_id="p_b", text="also went well")

    actions = process_due_summary_merges(db_session, now=datetime.now(UTC))

    assert len(actions) == 1
    assert actions[0]["entry_count"] == 2
    assert "went well" in actions[0]["digest"]
    assert "also went well" in actions[0]["digest"]
    db_session.refresh(order)
    assert order.status == "complete"


def test_action_item_in_a_dump_spawns_a_task(db_session, org, requester):
    order = request_summary(db_session, principal=requester, topic="sprint retro")
    submit_summary_entry(
        db_session, order_id=order.id, principal_id="p_a", text="- rotate the API key"
    )
    submit_summary_entry(db_session, order_id=order.id, principal_id="p_b", text="no actions here")

    actions = process_due_summary_merges(db_session, now=datetime.now(UTC))

    assert len(actions[0]["task_ids"]) == 1
    task = db_session.query(Task).filter(Task.id == actions[0]["task_ids"][0]).one()
    assert task.title == "rotate the API key"
    assert task.order_id == order.id


def test_merge_fires_at_scaled_t_plus_24h_with_zero_or_one_submission(
    db_session, org, requester, monkeypatch
):
    monkeypatch.setattr(config_module.settings, "nudge_time_scale", 1 / 60)  # 24h -> 24min
    order = request_summary(db_session, principal=requester, topic="sprint retro")
    submit_summary_entry(db_session, order_id=order.id, principal_id="p_a", text="one dump only")

    too_early = process_due_summary_merges(
        db_session, now=datetime.now(UTC) + timedelta(minutes=10)
    )
    assert too_early == []

    on_deadline = process_due_summary_merges(
        db_session, now=datetime.now(UTC) + timedelta(minutes=25)
    )
    assert len(on_deadline) == 1
    assert on_deadline[0]["entry_count"] == 1


def test_chase_nudges_requester_once_when_no_submissions_by_half_deadline(
    db_session, org, requester, monkeypatch
):
    monkeypatch.setattr(config_module.settings, "nudge_time_scale", 1 / 60)  # half-deadline -> 12min
    order = request_summary(db_session, principal=requester, topic="sprint retro")

    too_early = process_due_summary_chases(
        db_session, now=datetime.now(UTC) + timedelta(minutes=5)
    )
    assert too_early == []

    first = process_due_summary_chases(
        db_session, now=datetime.now(UTC) + timedelta(minutes=15)
    )
    assert len(first) == 1

    second = process_due_summary_chases(
        db_session, now=datetime.now(UTC) + timedelta(minutes=20)
    )
    assert second == []

    chase_nudges = list_nudges(db_session, order_id=order.id, kind=NudgeKind.SUMMARY_CHASE.value)
    assert len(chase_nudges) == 1
