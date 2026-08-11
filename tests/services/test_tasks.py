"""Unit tests for task decomposition, assignment, and ACK/BLOCKED transitions."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import (
    Base,
    NudgeKind,
    Org,
    Population,
    Principal,
    Task,
    TaskStatus,
)
from cerebro.services.nudges import list_nudges
from cerebro.services.orders import open_order
from cerebro.services.tasks import (
    CandidateView,
    ack_task,
    assign_task,
    block_task,
    create_task,
    decompose_order,
    decompose_order_text,
    select_assignee,
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


def _principal(db_session, org, *, id, population, skills=None, wip_cap=3):
    import json

    principal = Principal(
        id=id,
        org_id=org.id,
        population=population,
        skills_json=json.dumps(skills or []),
        wip_cap=wip_cap,
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()
    return principal


# --- Pure filter chain: designation -> skills -> wip_cap -> lowest load ---


def test_select_assignee_filters_by_designation_first():
    """A candidate outside the required designation is never eligible."""
    candidates = [
        CandidateView("p_ops", "ops", frozenset(), 3, 0),
        CandidateView("p_dev", "dev", frozenset(), 3, 0),
    ]
    assert select_assignee(candidates, designation="dev") == "p_dev"


def test_select_assignee_filters_by_skills_second():
    """Right designation but missing a required skill is excluded."""
    candidates = [
        CandidateView("p_no_skill", "dev", frozenset({"python"}), 3, 0),
        CandidateView("p_has_skill", "dev", frozenset({"python", "rust"}), 3, 0),
    ]
    assert (
        select_assignee(candidates, designation="dev", required_skills=["rust"])
        == "p_has_skill"
    )


def test_select_assignee_filters_by_wip_cap_third():
    """Right designation and skills but at wip_cap is excluded."""
    candidates = [
        CandidateView("p_full", "dev", frozenset(), 2, 2),
        CandidateView("p_open", "dev", frozenset(), 2, 1),
    ]
    assert select_assignee(candidates, designation="dev") == "p_open"


def test_select_assignee_picks_lowest_load_last():
    """Among equally eligible candidates, the lowest current load wins."""
    candidates = [
        CandidateView("p_busy", "dev", frozenset(), 5, 3),
        CandidateView("p_idle", "dev", frozenset(), 5, 0),
        CandidateView("p_mid", "dev", frozenset(), 5, 1),
    ]
    assert select_assignee(candidates, designation="dev") == "p_idle"


def test_select_assignee_ties_broken_deterministically_by_id():
    """Equal load ties break on principal_id for determinism."""
    candidates = [
        CandidateView("p_b", "dev", frozenset(), 5, 0),
        CandidateView("p_a", "dev", frozenset(), 5, 0),
    ]
    assert select_assignee(candidates, designation="dev") == "p_a"


def test_select_assignee_no_eligible_candidates_returns_none():
    assert select_assignee([], designation="dev") is None


# --- decompose_order ---


def test_decompose_order_text_splits_on_and_and_semicolons():
    titles = decompose_order_text("write the doc; and ship the release", "general")
    assert titles == ["write the doc", "ship the release"]


def test_decompose_order_creates_one_task_per_split(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    order = open_order(
        db_session,
        principal=client,
        text="draft the proposal and schedule the kickoff",
        order_type="general",
    )
    tasks = decompose_order(db_session, order, designation="dev")
    assert len(tasks) == 2
    assert {t.title for t in tasks} == {"draft the proposal", "schedule the kickoff"}
    assert all(t.status == TaskStatus.OPEN.value for t in tasks)
    assert all(t.order_id == order.id for t in tasks)


def test_task_numbers_increment_per_org(db_session, org):
    t1 = create_task(db_session, org_id=org.id, title="a", designation="dev")
    t2 = create_task(db_session, org_id=org.id, title="b", designation="dev")
    assert t2.number == t1.number + 1


# --- assign_task (DB-backed wrapper) ---


def test_assign_task_end_to_end_chooses_lowest_load(db_session, org):
    _principal(db_session, org, id="p_ops", population=Population.OPS)
    _principal(db_session, org, id="p_dev_busy", population=Population.DEV)
    _principal(db_session, org, id="p_dev_idle", population=Population.DEV)
    task = create_task(db_session, org_id=org.id, title="fix bug", designation="dev")
    other = create_task(db_session, org_id=org.id, title="other bug", designation="dev")
    other.assignee_principal_id = "p_dev_busy"
    db_session.commit()

    assignee = assign_task(db_session, task)

    assert assignee.id == "p_dev_idle"
    assert task.assignee_principal_id == "p_dev_idle"


def test_assign_task_no_eligible_returns_none(db_session, org):
    task = create_task(db_session, org_id=org.id, title="fix bug", designation="dev")
    assert assign_task(db_session, task) is None
    assert task.assignee_principal_id is None


# --- send_task_card / ACK / BLOCKED ---


def test_send_task_card_creates_nudge_and_arms_ladder(db_session, org):
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    task = create_task(db_session, org_id=org.id, title="ship it", designation="dev")
    task.assignee_principal_id = dev.id
    db_session.commit()

    nudge = send_task_card(db_session, task)

    assert nudge.kind == NudgeKind.TASK_CARD.value
    assert str(task.number) in nudge.body
    assert task.ladder_rung == 1
    assert task.ladder_next_due_at is not None


def test_ack_task_cancels_remaining_ladder_rungs(db_session, org):
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    task = create_task(db_session, org_id=org.id, title="ship it", designation="dev")
    task.assignee_principal_id = dev.id
    db_session.commit()
    send_task_card(db_session, task)

    acked = ack_task(db_session, org_id=org.id, number=task.number)

    assert acked.status == TaskStatus.ACKED.value
    assert acked.ladder_status == "cancelled"
    assert acked.ladder_next_due_at is None
    assert acked.acked_at is not None


def test_ack_task_unknown_number_returns_none(db_session, org):
    assert ack_task(db_session, org_id=org.id, number=999) is None


def test_block_task_notifies_org_leads(db_session, org):
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    lead = _principal(db_session, org, id="p_lead", population=Population.LEAD)
    task = create_task(db_session, org_id=org.id, title="ship it", designation="dev")
    task.assignee_principal_id = dev.id
    db_session.commit()

    blocked = block_task(
        db_session, org_id=org.id, number=task.number, principal=dev, reason="waiting on API keys"
    )

    assert blocked.status == TaskStatus.BLOCKED.value
    assert blocked.blocked_reason == "waiting on API keys"
    lead_nudges = list_nudges(db_session, kind=NudgeKind.TASK_BLOCKED.value)
    assert len(lead_nudges) == 1
    assert lead_nudges[0].principal_id == lead.id
    assert "waiting on API keys" in lead_nudges[0].body


def test_three_devs_get_three_different_tasks(db_session, org):
    """Assignment filter chain distributes across devs by lowest load."""
    for name in ("p_dev_1", "p_dev_2", "p_dev_3"):
        _principal(db_session, org, id=name, population=Population.DEV)

    tasks = [
        create_task(db_session, org_id=org.id, title=f"task {i}", designation="dev")
        for i in range(3)
    ]
    assignees = {assign_task(db_session, task).id for task in tasks}

    assert len(assignees) == 3
