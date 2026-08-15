"""Unit tests for the automatic order-intake pipeline (decompose + assign +
raise a Jira ticket) - the piece that was missing: opening an order used to
just sit at status=open, unassigned, with no ticket, until a team member
noticed and called the tools by hand."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population, Principal, Task, TaskStatus
from cerebro.services.order_intake import infer_designation, process_new_orders
from cerebro.services.orders import open_order


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def jira_configured(monkeypatch):
    """Pin the Jira project key explicitly rather than relying on whatever
    happens to be in the ambient .env, matching tests/jira/test_api.py."""
    monkeypatch.setattr("cerebro.config.settings.jira_default_project_key", "PROJ")


@pytest.fixture
def org(db_session):
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def _principal(db_session, org, *, id, population):
    principal = Principal(id=id, org_id=org.id, population=population, created_at=datetime.now(UTC))
    db_session.add(principal)
    db_session.commit()
    return principal


class _FakeJira:
    def __init__(self, *, key: str = "PROJ-1", fail: bool = False):
        self.key = key
        self.fail = fail
        self.calls: list[dict] = []

    def create_issue(self, project_key, *, summary, description="", issue_type="Task", labels=None):
        self.calls.append({"project_key": project_key, "summary": summary})
        if self.fail:
            from cerebro.jira.api import JiraAPIError

            raise JiraAPIError("boom")
        return {"key": self.key}


# --- infer_designation (pure) ---


def test_infer_designation_matches_dev_keywords():
    assert infer_designation("frontend_development", "fix the frontend bug") == "dev"


def test_infer_designation_matches_ops_keywords():
    assert infer_designation("general", "please deploy this to prod") == "ops"


def test_infer_designation_defaults_to_ops_when_nothing_matches():
    assert infer_designation("general", "something vague and unrelated") == "ops"


# --- process_new_orders ---


def test_process_new_orders_decomposes_and_assigns(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    order = open_order(db_session, principal=client, text="the frontend for my app is broken")

    actions = process_new_orders(db_session, jira_client=_FakeJira())

    assert len(actions) == 1
    assert actions[0]["order_id"] == order.id
    assert actions[0]["designation"] == "dev"
    assert actions[0]["assigned_task_numbers"]
    assert actions[0]["jira_key"] == "PROJ-1"

    tasks = db_session.query(Task).filter(Task.order_id == order.id).all()
    assert len(tasks) >= 1
    assert tasks[0].assignee_principal_id == dev.id
    assert tasks[0].status == TaskStatus.OPEN.value

    db_session.refresh(order)
    assert order.status == "in_progress"

    from cerebro.services.orders import loads_fields

    assert loads_fields(order.fields_json)["jira_key"] == "PROJ-1"


def test_process_new_orders_is_idempotent(db_session, org):
    """A second tick must not re-decompose an order that already has tasks."""
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    _principal(db_session, org, id="p_dev", population=Population.DEV)
    open_order(db_session, principal=client, text="fix a frontend bug")

    first = process_new_orders(db_session, jira_client=_FakeJira())
    second = process_new_orders(db_session, jira_client=_FakeJira())

    assert len(first) == 1
    assert second == []


def test_process_new_orders_handles_no_eligible_assignee(db_session, org):
    """No dev on the team yet: task is created but stays unassigned, and the
    tick still completes (doesn't raise or skip the Jira ticket)."""
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    order = open_order(db_session, principal=client, text="fix a frontend bug")

    actions = process_new_orders(db_session, jira_client=_FakeJira())

    assert actions[0]["assigned_task_numbers"] == []
    tasks = db_session.query(Task).filter(Task.order_id == order.id).all()
    assert tasks[0].assignee_principal_id is None


def test_process_new_orders_skips_jira_when_unconfigured(db_session, org, monkeypatch):
    monkeypatch.setattr("cerebro.config.settings.jira_default_project_key", "")
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    _principal(db_session, org, id="p_dev", population=Population.DEV)
    open_order(db_session, principal=client, text="fix a frontend bug")
    fake = _FakeJira()

    actions = process_new_orders(db_session, jira_client=fake)

    assert actions[0]["jira_key"] is None
    assert fake.calls == []


def test_process_new_orders_survives_jira_failure(db_session, org):
    """A broken Jira integration must not block decomposition/assignment."""
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    _principal(db_session, org, id="p_dev", population=Population.DEV)
    open_order(db_session, principal=client, text="fix a frontend bug")

    actions = process_new_orders(db_session, jira_client=_FakeJira(fail=True))

    assert actions[0]["jira_key"] is None
    assert actions[0]["assigned_task_numbers"]
