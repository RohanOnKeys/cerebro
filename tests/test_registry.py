"""Unit tests for the population-gated tool registry."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population, Principal
from cerebro.registry import TOOLS, TOOLS_FOR, tools_for


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()


@pytest.fixture
def client_principal(db_session):
    """Create a CLIENT principal for handler tests."""
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    principal = Principal(
        id="principal_client",
        org_id="org_1",
        population=Population.CLIENT,
        email="client@test.com",
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def test_tools_for_client_excludes_enroll_principal():
    """CLIENT tool list must not include team/ops-only enroll_principal."""
    names = {tool.name for tool in TOOLS_FOR[Population.CLIENT]}

    assert "whoami" in names
    assert "set_availability" in names
    assert "enroll_principal" not in names


def test_tools_for_ops_includes_enroll_principal():
    """OPS (team) tool list includes enroll_principal."""
    names = {tool.name for tool in TOOLS_FOR[Population.OPS]}

    assert "enroll_principal" in names
    assert "whoami" in names
    assert "set_availability" in names


def test_tools_for_helper_matches_mapping():
    """tools_for() mirrors TOOLS_FOR for each population."""
    for population in Population:
        assert tools_for(population) == TOOLS_FOR[population]


def test_enroll_principal_allowed_populations_are_team_only():
    """enroll_principal is gated to OPS/DEV/LEAD/ADMIN only."""
    allowed = TOOLS["enroll_principal"].allowed_populations

    assert Population.CLIENT not in allowed
    assert allowed == frozenset(
        {Population.OPS, Population.DEV, Population.LEAD, Population.ADMIN}
    )


def test_whoami_handler_returns_identity(client_principal):
    """whoami handler returns principal identity fields."""
    result = TOOLS["whoami"].handler(principal=client_principal)

    assert result["principal_id"] == "principal_client"
    assert result["population"] == Population.CLIENT.value
    assert result["org_id"] == "org_1"
    assert result["email"] == "client@test.com"


def test_set_availability_handler(client_principal):
    """set_availability handler acknowledges availability for a principal."""
    result = TOOLS["set_availability"].handler(
        principal=client_principal, available=False, note="out of office"
    )

    assert result["principal_id"] == "principal_client"
    assert result["available"] is False
    assert result["note"] == "out of office"
    assert result["status"] == "recorded"


def test_enroll_principal_handler_uses_enrollment_service(db_session, client_principal):
    """enroll_principal handler wraps enroll_unknown_sender."""
    # client_principal fixture ensures org_1 exists
    _ = client_principal
    caller = Principal(
        id="p_ops_enroll",
        org_id="org_1",
        population=Population.OPS,
        created_at=datetime.now(UTC),
    )
    db_session.add(caller)
    db_session.commit()

    result = TOOLS["enroll_principal"].handler(
        session=db_session,
        principal=caller,
        org_id="org_1",
        channel="telegram",
        channel_id="999888",
        conversation_id="conv_registry_1",
    )

    assert result["population"] == Population.CLIENT.value
    assert result["verified"] == "verified"
    assert result["principal_id"]
    assert result["binding_id"]


def test_enroll_principal_handler_defaults_org_id_to_caller_org(db_session):
    """org_id is optional - a team member enrolling a new contact adds them to
    their own org by default, not an arbitrary org_id they'd have to know and
    type. (The bug this fixes: asked to "enroll me" by an already-known
    sender, the model fell back to asking for org_id/channel_id and then
    created a disconnected, garbage org out of whatever the user guessed.)"""
    org = Org(id="org_caller", name="Caller Org", join_code="CALLERORG", created_at=datetime.now(UTC))
    db_session.add(org)
    caller = Principal(
        id="p_ops_caller", org_id="org_caller", population=Population.OPS,
        created_at=datetime.now(UTC),
    )
    db_session.add(caller)
    db_session.commit()

    result = TOOLS["enroll_principal"].handler(
        session=db_session,
        principal=caller,
        channel="discord",
        channel_id="dc-999",
        conversation_id="conv_default_org",
    )

    new_principal = db_session.query(Principal).filter(Principal.id == result["principal_id"]).one()
    assert new_principal.org_id == "org_caller"


def test_reminder_system_client_only_gets_request_deadline():
    """The one reminder-system tool CLIENT has access to."""
    names = {tool.name for tool in TOOLS_FOR[Population.CLIENT]}

    assert "request_deadline" in names
    assert "set_reminder" not in names
    assert "list_reminders" not in names
    assert "cancel_reminder" not in names
    assert "calendar_view" not in names


def test_reminder_system_team_gets_everything():
    names = {tool.name for tool in TOOLS_FOR[Population.OPS]}

    for tool_name in (
        "request_deadline",
        "set_reminder",
        "list_reminders",
        "cancel_reminder",
        "calendar_view",
    ):
        assert tool_name in names


def test_set_reminder_handler_defaults_target_to_caller(db_session):
    org = Org(id="org_2", name="Org 2", join_code="ORGTWO", created_at=datetime.now(UTC))
    db_session.add(org)
    ops = Principal(
        id="p_ops", org_id="org_2", population=Population.OPS, created_at=datetime.now(UTC)
    )
    db_session.add(ops)
    db_session.commit()

    result = TOOLS["set_reminder"].handler(
        session=db_session,
        principal=ops,
        subject="check on the client",
        due_at="2026-08-20T12:00:00+00:00",
    )

    assert result["principal_id"] == "p_ops"
    assert result["kind"] == "general"
    assert result["status"] == "pending"


def test_request_deadline_handler_notifies_assignee(db_session):
    from cerebro.db.models import Order, Task

    org = Org(id="org_3", name="Org 3", join_code="ORGTHREE", created_at=datetime.now(UTC))
    db_session.add(org)
    client = Principal(
        id="p_client3", org_id="org_3", population=Population.CLIENT, created_at=datetime.now(UTC)
    )
    dev = Principal(
        id="p_dev3", org_id="org_3", population=Population.DEV, created_at=datetime.now(UTC)
    )
    db_session.add_all([client, dev])
    order = Order(
        id="order_3",
        org_id="org_3",
        principal_id="p_client3",
        order_type="general",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(order)
    task = Task(
        id="task_3",
        org_id="org_3",
        order_id="order_3",
        number=1,
        title="do it",
        designation="dev",
        assignee_principal_id="p_dev3",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(task)
    db_session.commit()

    result = TOOLS["request_deadline"].handler(
        session=db_session,
        principal=client,
        order_id="order_3",
        due_at="2026-08-22T09:00:00+00:00",
        note="need this for a client demo",
    )

    assert result["order_id"] == "order_3"
    assert len(result["reminders"]) == 1
    assert result["reminders"][0]["principal_id"] == "p_dev3"
    assert result["reminders"][0]["kind"] == "deadline"


def test_request_deadline_handler_unknown_order_errors(db_session, client_principal):
    result = TOOLS["request_deadline"].handler(
        session=db_session,
        principal=client_principal,
        order_id="nope",
        due_at="2026-08-22T09:00:00+00:00",
    )

    assert result["error"] == "order_not_found"


def test_set_reminder_handler_in_seconds_is_computed_server_side(db_session):
    """The bug this fixes: the model's own arithmetic (plus response
    latency) can drift a relative offset - asked for 30s, landed on 8s
    live. in_seconds sidesteps that by computing from the real clock at
    the moment the tool actually runs, not from a value the model derived
    earlier in its own turn."""
    from datetime import timedelta

    org = Org(id="org_secs", name="Org", join_code="ORGSECS", created_at=datetime.now(UTC))
    db_session.add(org)
    ops = Principal(
        id="p_ops_secs", org_id="org_secs", population=Population.OPS,
        created_at=datetime.now(UTC),
    )
    db_session.add(ops)
    db_session.commit()

    before = datetime.now(UTC)
    result = TOOLS["set_reminder"].handler(
        session=db_session, principal=ops, subject="check email", in_seconds=30
    )
    after = datetime.now(UTC)

    due_at = datetime.fromisoformat(result["due_at"])
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    assert before + timedelta(seconds=30) <= due_at <= after + timedelta(seconds=30)


def test_set_reminder_handler_rejects_non_positive_in_seconds(db_session, client_principal):
    result = TOOLS["set_reminder"].handler(
        session=db_session,
        principal=client_principal,
        subject="x",
        in_seconds=0,
    )

    assert result["error"] == "invalid_due_at_or_in_seconds"


def test_set_reminder_handler_requires_due_at_or_in_seconds(db_session, client_principal):
    result = TOOLS["set_reminder"].handler(
        session=db_session, principal=client_principal, subject="x"
    )

    assert result["error"] == "invalid_due_at_or_in_seconds"


def test_request_deadline_handler_accepts_in_seconds(db_session):
    from datetime import UTC, datetime

    from cerebro.db.models import Order, Task

    org = Org(id="org_secs2", name="Org", join_code="ORGSECS2", created_at=datetime.now(UTC))
    db_session.add(org)
    client = Principal(
        id="p_client_secs", org_id="org_secs2", population=Population.CLIENT,
        created_at=datetime.now(UTC),
    )
    dev = Principal(
        id="p_dev_secs", org_id="org_secs2", population=Population.DEV,
        created_at=datetime.now(UTC),
    )
    db_session.add_all([client, dev])
    order = Order(
        id="order_secs", org_id="org_secs2", principal_id="p_client_secs",
        order_type="general", created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    db_session.add(order)
    task = Task(
        id="task_secs", org_id="org_secs2", order_id="order_secs", number=1,
        title="do it", designation="dev", assignee_principal_id="p_dev_secs",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    db_session.add(task)
    db_session.commit()

    result = TOOLS["request_deadline"].handler(
        session=db_session, principal=client, order_id="order_secs", in_seconds=60
    )

    assert "error" not in result
    assert result["reminders"][0]["principal_id"] == "p_dev_secs"


def test_create_team_allowed_populations_are_team_only():
    allowed = TOOLS["create_team"].allowed_populations

    assert Population.CLIENT not in allowed
    assert allowed == frozenset(
        {Population.OPS, Population.DEV, Population.LEAD, Population.ADMIN}
    )


def test_create_team_handler_auto_generates_code(db_session, client_principal):
    result = TOOLS["create_team"].handler(
        session=db_session, principal=client_principal, name="Acme Inc"
    )

    assert result["name"] == "Acme Inc"
    assert "join_code" in result and len(result["join_code"]) == 6
    org = db_session.query(Org).filter(Org.id == result["org_id"]).one()
    assert org.name == "Acme Inc"
    assert org.join_code == result["join_code"]


def test_create_team_handler_accepts_explicit_code(db_session, client_principal):
    result = TOOLS["create_team"].handler(
        session=db_session, principal=client_principal, name="Acme Inc", code="acme-hq"
    )

    assert result["join_code"] == "ACME-HQ"


def test_create_team_handler_rejects_code_already_in_use(db_session, client_principal):
    """A CREATE that names an existing team's code is refused, not silently
    treated as joining that other team."""
    first = TOOLS["create_team"].handler(
        session=db_session, principal=client_principal, name="Acme Inc", code="TAKEN"
    )
    assert "error" not in first

    second = TOOLS["create_team"].handler(
        session=db_session, principal=client_principal, name="Someone Else", code="taken"
    )

    assert second["error"] == "code_already_in_use"
    assert second["code"] == "TAKEN"
