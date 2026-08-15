"""Unit tests for the self-hosted reminder/deadline system."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import (
    Base,
    Order,
    Org,
    Population,
    Principal,
    ReminderKind,
    ReminderStatus,
    Task,
)
from cerebro.services.nudges import list_nudges
from cerebro.services.reminders import (
    cancel_reminder,
    create_reminder,
    list_reminders,
    process_due_reminders,
    resolve_deadline_targets,
    serialize_reminder,
)

NOON = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


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
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def _principal(db_session, org, *, id, population=Population.OPS):
    principal = Principal(id=id, org_id=org.id, population=population, created_at=NOON)
    db_session.add(principal)
    db_session.commit()
    return principal


def _order(db_session, org, principal):
    order = Order(
        id="order_1",
        org_id=org.id,
        principal_id=principal.id,
        order_type="general",
        created_at=NOON,
        updated_at=NOON,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_create_reminder_persists_pending_row(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)

    reminder = create_reminder(
        db_session,
        org_id=org.id,
        created_by_principal_id=client.id,
        principal_id=client.id,
        subject="follow up",
        due_at=NOON + timedelta(hours=1),
    )

    assert reminder.status == ReminderStatus.PENDING.value
    assert reminder.kind == ReminderKind.GENERAL.value
    row = serialize_reminder(reminder)
    assert row["subject"] == "follow up"


def test_resolve_deadline_targets_prefers_assignee(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    lead = _principal(db_session, org, id="p_lead", population=Population.LEAD)
    order = _order(db_session, org, client)
    task = Task(
        id="task_1",
        org_id=org.id,
        order_id=order.id,
        number=1,
        title="Do the thing",
        designation="dev",
        assignee_principal_id=dev.id,
        created_at=NOON,
        updated_at=NOON,
    )
    db_session.add(task)
    db_session.commit()

    targets = resolve_deadline_targets(db_session, org_id=org.id, order_id=order.id)

    assert [t.id for t in targets] == [dev.id]
    assert lead.id not in [t.id for t in targets]


def test_resolve_deadline_targets_falls_back_to_leads_when_unassigned(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    lead1 = _principal(db_session, org, id="p_lead1", population=Population.LEAD)
    lead2 = _principal(db_session, org, id="p_lead2", population=Population.LEAD)
    order = _order(db_session, org, client)

    targets = resolve_deadline_targets(db_session, org_id=org.id, order_id=order.id)

    assert {t.id for t in targets} == {lead1.id, lead2.id}


def test_process_due_reminders_fires_only_past_due_pending(db_session, org):
    ops = _principal(db_session, org, id="p_ops")
    due_now = create_reminder(
        db_session,
        org_id=org.id,
        created_by_principal_id=ops.id,
        principal_id=ops.id,
        subject="due now",
        due_at=NOON,
    )
    not_due_yet = create_reminder(
        db_session,
        org_id=org.id,
        created_by_principal_id=ops.id,
        principal_id=ops.id,
        subject="later",
        due_at=NOON + timedelta(hours=2),
    )

    fired = process_due_reminders(db_session, now=NOON + timedelta(minutes=1))

    fired_ids = {f["reminder_id"] for f in fired}
    assert due_now.id in fired_ids
    assert not_due_yet.id not in fired_ids

    db_session.refresh(due_now)
    db_session.refresh(not_due_yet)
    assert due_now.status == ReminderStatus.FIRED.value
    assert due_now.fired_at is not None
    assert not_due_yet.status == ReminderStatus.PENDING.value

    nudges = list_nudges(db_session)
    assert any(n.principal_id == ops.id for n in nudges)


def test_process_due_reminders_does_not_refire_already_fired(db_session, org):
    ops = _principal(db_session, org, id="p_ops")
    reminder = create_reminder(
        db_session,
        org_id=org.id,
        created_by_principal_id=ops.id,
        principal_id=ops.id,
        subject="once",
        due_at=NOON,
    )

    first = process_due_reminders(db_session, now=NOON + timedelta(minutes=1))
    second = process_due_reminders(db_session, now=NOON + timedelta(hours=5))

    assert len(first) == 1
    assert second == []


def test_list_reminders_filters_by_principal_and_status(db_session, org):
    ops = _principal(db_session, org, id="p_ops")
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    create_reminder(
        db_session, org_id=org.id, created_by_principal_id=ops.id,
        principal_id=ops.id, subject="mine", due_at=NOON,
    )
    create_reminder(
        db_session, org_id=org.id, created_by_principal_id=ops.id,
        principal_id=dev.id, subject="not mine", due_at=NOON,
    )

    mine = list_reminders(db_session, org_id=org.id, principal_id=ops.id)
    everyone = list_reminders(db_session, org_id=org.id, principal_id=None)

    assert [r.subject for r in mine] == ["mine"]
    assert len(everyone) == 2


def test_cancel_reminder_marks_cancelled_and_is_idempotent_guarded(db_session, org):
    ops = _principal(db_session, org, id="p_ops")
    reminder = create_reminder(
        db_session, org_id=org.id, created_by_principal_id=ops.id,
        principal_id=ops.id, subject="skip this", due_at=NOON,
    )

    cancelled = cancel_reminder(db_session, org_id=org.id, reminder_id=reminder.id)
    again = cancel_reminder(db_session, org_id=org.id, reminder_id=reminder.id)

    assert cancelled.status == ReminderStatus.CANCELLED.value
    assert again is None  # already cancelled, not pending anymore

    fired = process_due_reminders(db_session, now=NOON + timedelta(hours=1))
    assert fired == []
