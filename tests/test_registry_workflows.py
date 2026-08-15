"""cancel_meeting, route_client_feedback, post_incident_update tool coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Nudge, Org, Population, Principal
from cerebro.membrane.policy import seed_default_policies
from cerebro.registry import TOOLS
from cerebro.services.meetings import schedule_meeting
from cerebro.services.tasks import create_task


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_default_policies(session)
    yield session
    session.close()


@pytest.fixture
def org(db_session):
    org = Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def _principal(db_session, org, *, id, population):
    principal = Principal(
        id=id, org_id=org.id, population=population, created_at=datetime.now(UTC)
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def test_cancel_meeting_by_organizer_notifies_attendees(db_session, org):
    organizer = _principal(db_session, org, id="p_organizer", population=Population.DEV)
    attendee = _principal(db_session, org, id="p_attendee", population=Population.DEV)
    meeting = schedule_meeting(
        db_session,
        org_id=org.id,
        organizer_principal_id=organizer.id,
        title="Standup",
        starts_at=datetime.now(UTC) + timedelta(hours=1),
        attendee_principal_ids=[attendee.id],
    )

    result = TOOLS["cancel_meeting"].handler(
        session=db_session, principal=organizer, meeting_id=meeting.id
    )

    assert result["status"] == "cancelled"
    nudges = db_session.query(Nudge).filter(Nudge.kind == "meeting_cancelled").all()
    assert {n.principal_id for n in nudges} == {organizer.id, attendee.id}


def test_cancel_meeting_refuses_non_organizer(db_session, org):
    organizer = _principal(db_session, org, id="p_organizer", population=Population.DEV)
    other = _principal(db_session, org, id="p_other", population=Population.DEV)
    meeting = schedule_meeting(
        db_session,
        org_id=org.id,
        organizer_principal_id=organizer.id,
        title="Standup",
        starts_at=datetime.now(UTC) + timedelta(hours=1),
    )

    result = TOOLS["cancel_meeting"].handler(
        session=db_session, principal=other, meeting_id=meeting.id
    )

    assert result["error"] == "not_organizer"


def test_route_client_feedback_reaches_task_assignee(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    task = create_task(db_session, org_id=org.id, title="Fix bug", designation="dev")
    task.assignee_principal_id = dev.id
    db_session.commit()

    result = TOOLS["route_client_feedback"].handler(
        session=db_session,
        principal=client,
        text="the export button is broken",
        task_number=task.number,
    )

    assert result["routed_to"] == dev.id
    assert result["action"] == "allow"
    nudge = db_session.query(Nudge).filter(Nudge.principal_id == dev.id).one()
    assert "export button is broken" in nudge.body
    assert nudge.kind == "client_feedback"


def test_route_client_feedback_falls_back_to_leads_when_unassigned(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)
    lead = _principal(db_session, org, id="p_lead", population=Population.LEAD)
    task = create_task(db_session, org_id=org.id, title="Unassigned work", designation="dev")

    result = TOOLS["route_client_feedback"].handler(
        session=db_session,
        principal=client,
        text="still waiting on this",
        task_number=task.number,
    )

    assert result["action"] == "escalated_to_leads"
    assert result["routed_to"] == [lead.id]
    nudge = db_session.query(Nudge).filter(Nudge.principal_id == lead.id).one()
    assert "unassigned" in nudge.body.lower()


def test_route_client_feedback_unknown_task_errors(db_session, org):
    client = _principal(db_session, org, id="p_client", population=Population.CLIENT)

    result = TOOLS["route_client_feedback"].handler(
        session=db_session, principal=client, text="hello", task_number=999
    )

    assert result["error"] == "task_not_found"


def test_post_incident_update_broadcasts_to_population(db_session, org):
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)
    ops_1 = _principal(db_session, org, id="p_ops_1", population=Population.OPS)
    ops_2 = _principal(db_session, org, id="p_ops_2", population=Population.OPS)

    result = TOOLS["post_incident_update"].handler(
        session=db_session,
        principal=dev,
        summary="staging db is down",
        target_population="ops",
        severity="critical",
    )

    assert set(result["notified"]) == {ops_1.id, ops_2.id}
    nudges = db_session.query(Nudge).filter(Nudge.kind == "incident_update").all()
    assert len(nudges) == 2
    assert all("staging db is down" in n.body for n in nudges)
    assert all("CRITICAL" in n.body for n in nudges)


def test_post_incident_update_no_recipients(db_session, org):
    dev = _principal(db_session, org, id="p_dev", population=Population.DEV)

    result = TOOLS["post_incident_update"].handler(
        session=db_session,
        principal=dev,
        summary="nobody to tell",
        target_population="admin",
    )

    assert result["error"] == "no_recipients"


def test_route_client_feedback_and_post_incident_update_are_registered():
    assert TOOLS["route_client_feedback"].allowed_populations == frozenset(Population)
    assert Population.CLIENT not in TOOLS["post_incident_update"].allowed_populations
