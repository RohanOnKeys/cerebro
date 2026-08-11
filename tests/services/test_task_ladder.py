"""Integration tests for the task ladder clock job."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import (
    Base,
    ChannelBinding,
    NudgeKind,
    Org,
    Population,
    Principal,
    Task,
)
from cerebro.services.nudges import list_nudges
from cerebro.services.tasks import (
    ack_task,
    assign_task,
    create_task,
    process_due_task_ladders,
    send_task_card,
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
def dev(db_session, org):
    principal = Principal(
        id="p_dev",
        org_id=org.id,
        population=Population.DEV,
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.add(
        ChannelBinding(
            id="b_1",
            principal_id="p_dev",
            channel="discord",
            channel_id="discord_dev",
            verified="verified",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    return principal


def test_ladder_tick_before_gap_elapsed_does_not_nudge(db_session, org, dev):
    task = create_task(db_session, org_id=org.id, title="ship it", designation="dev")
    task.assignee_principal_id = dev.id
    db_session.commit()
    send_task_card(db_session, task)

    now = datetime.now(UTC)
    actions = process_due_task_ladders(db_session, now=now + timedelta(minutes=5))

    assert actions == []


def test_ladder_tick_after_gap_sends_coalesced_nudge(db_session, org, dev):
    task = create_task(db_session, org_id=org.id, title="ship it", designation="dev")
    task.assignee_principal_id = dev.id
    db_session.commit()
    send_task_card(db_session, task)

    due_at = task.ladder_next_due_at
    actions = process_due_task_ladders(db_session, now=due_at)

    assert len(actions) == 1
    assert actions[0]["task_numbers"] == [task.number]
    ladder_nudges = list_nudges(db_session, kind=NudgeKind.TASK_LADDER.value)
    assert len(ladder_nudges) == 1
    assert str(task.number) in ladder_nudges[0].body


def test_ack_before_due_suppresses_further_ladder_nudges(db_session, org, dev):
    task = create_task(db_session, org_id=org.id, title="ship it", designation="dev")
    task.assignee_principal_id = dev.id
    db_session.commit()
    send_task_card(db_session, task)

    ack_task(db_session, org_id=org.id, number=task.number)

    due_at = task.ladder_last_fired_at + timedelta(days=2)
    actions = process_due_task_ladders(db_session, now=due_at)

    assert actions == []
    assert list_nudges(db_session, kind=NudgeKind.TASK_LADDER.value) == []


def test_unreachable_assignee_with_no_verified_binding_is_skipped(db_session, org):
    unreachable = Principal(
        id="p_no_binding",
        org_id=org.id,
        population=Population.DEV,
        created_at=datetime.now(UTC),
    )
    db_session.add(unreachable)
    db_session.commit()
    task = create_task(db_session, org_id=org.id, title="ship it", designation="dev")
    task.assignee_principal_id = unreachable.id
    db_session.commit()
    send_task_card(db_session, task)

    actions = process_due_task_ladders(db_session, now=task.ladder_next_due_at)

    assert actions == []


def test_multiple_due_tasks_for_same_principal_coalesce_into_one_nudge(db_session, org, dev):
    tasks = [
        create_task(db_session, org_id=org.id, title=f"task {i}", designation="dev")
        for i in range(2)
    ]
    for task in tasks:
        task.assignee_principal_id = dev.id
    db_session.commit()
    for task in tasks:
        send_task_card(db_session, task)

    latest_due = max(t.ladder_next_due_at for t in tasks)
    actions = process_due_task_ladders(db_session, now=latest_due)

    assert len(actions) == 1
    assert set(actions[0]["task_numbers"]) == {t.number for t in tasks}
    assert list_nudges(db_session, kind=NudgeKind.TASK_LADDER.value).__len__() == 1


def test_three_devs_get_task_cards_on_discord(db_session, org):
    devs = []
    for i in range(3):
        principal = Principal(
            id=f"p_dev_{i}",
            org_id=org.id,
            population=Population.DEV,
            created_at=datetime.now(UTC),
        )
        db_session.add(principal)
        db_session.add(
            ChannelBinding(
                id=f"b_{i}",
                principal_id=f"p_dev_{i}",
                channel="discord",
                channel_id=f"discord_{i}",
                verified="verified",
                created_at=datetime.now(UTC),
            )
        )
        devs.append(principal)
    db_session.commit()

    tasks = [
        create_task(db_session, org_id=org.id, title=f"task {i}", designation="dev")
        for i in range(3)
    ]
    for task in tasks:
        assignee = assign_task(db_session, task)
        assert assignee is not None
        send_task_card(db_session, task)

    assignees = {task.assignee_principal_id for task in tasks}
    assert assignees == {d.id for d in devs}
    assert list_nudges(db_session, kind=NudgeKind.TASK_CARD.value).__len__() == 3
