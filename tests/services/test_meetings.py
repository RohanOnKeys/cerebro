"""Unit tests for meeting scheduling, RSVP, find_slot, and scaled reminders."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro import config as config_module
from cerebro.db.models import (
    Base,
    ChannelBinding,
    NudgeKind,
    Org,
    Population,
    Principal,
)
from cerebro.services.meetings import (
    due_reminder_stage,
    find_slot,
    process_due_meeting_reminders,
    rsvp,
    schedule_meeting,
)
from cerebro.services.nudges import list_nudges

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
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
    db_session.add(org)
    db_session.commit()
    return org


def _principal(db_session, org, *, id, channels=()):
    principal = Principal(
        id=id, org_id=org.id, population=Population.DEV, created_at=datetime.now(UTC)
    )
    db_session.add(principal)
    for channel in channels:
        db_session.add(
            ChannelBinding(
                id=f"b_{id}_{channel}",
                principal_id=id,
                channel=channel,
                channel_id=f"{channel}_{id}",
                verified="verified",
                created_at=datetime.now(UTC),
            )
        )
    db_session.commit()
    return principal


# --- find_slot (pure) ---


def test_find_slot_rounds_up_to_next_half_hour():
    after = datetime(2026, 8, 11, 12, 5, tzinfo=UTC)
    slot = find_slot([], duration_minutes=30, after=after)
    assert slot == datetime(2026, 8, 11, 12, 30, tzinfo=UTC)


def test_find_slot_avoids_busy_interval():
    busy = [(NOON, NOON + timedelta(minutes=30))]
    slot = find_slot(busy, duration_minutes=30, after=NOON)
    assert slot == NOON + timedelta(minutes=30)


def test_find_slot_avoids_quiet_hours():
    late = datetime(2026, 8, 11, 23, 0, tzinfo=UTC)
    slot = find_slot([], duration_minutes=30, after=late)
    assert slot == datetime(2026, 8, 12, 8, 0, tzinfo=UTC)


# --- schedule_meeting / rsvp ---


def test_schedule_meeting_creates_attendee_rows_for_organizer_and_invitees(db_session, org):
    organizer = _principal(db_session, org, id="p_organizer")
    invitee = _principal(db_session, org, id="p_invitee")

    meeting = schedule_meeting(
        db_session,
        org_id=org.id,
        organizer_principal_id=organizer.id,
        title="planning sync",
        starts_at=NOON,
        attendee_principal_ids=[invitee.id],
    )

    from cerebro.db.models import MeetingAttendee

    attendees = (
        db_session.query(MeetingAttendee)
        .filter(MeetingAttendee.meeting_id == meeting.id)
        .all()
    )
    assert {a.principal_id for a in attendees} == {organizer.id, invitee.id}
    assert all(a.rsvp_status == "pending" for a in attendees)


def test_rsvp_updates_attendee_status(db_session, org):
    organizer = _principal(db_session, org, id="p_organizer")
    meeting = schedule_meeting(
        db_session,
        org_id=org.id,
        organizer_principal_id=organizer.id,
        title="planning sync",
        starts_at=NOON,
    )

    attendee = rsvp(
        db_session, meeting_id=meeting.id, principal_id=organizer.id, status="yes"
    )

    assert attendee.rsvp_status == "yes"


# --- due_reminder_stage (pure, scaled) ---


def test_due_reminder_stage_fires_in_order_as_time_advances():
    starts_at = NOON
    assert due_reminder_stage(starts_at, "none", now=starts_at - timedelta(days=2)) is None
    assert (
        due_reminder_stage(starts_at, "none", now=starts_at - timedelta(hours=24))
        == "t_minus_24h"
    )
    assert (
        due_reminder_stage(starts_at, "t_minus_24h", now=starts_at - timedelta(minutes=60))
        == "t_minus_60m"
    )
    assert (
        due_reminder_stage(starts_at, "t_minus_60m", now=starts_at - timedelta(minutes=10))
        == "t_minus_10m"
    )
    assert due_reminder_stage(starts_at, "t_minus_10m", now=starts_at) is None


def test_due_reminder_stage_scales_with_nudge_time_scale(monkeypatch):
    monkeypatch.setattr(config_module.settings, "nudge_time_scale", 1 / 60)
    starts_at = NOON
    # Scaled: 24h -> 24min, 60m -> 1min, 10m -> 10s.
    assert (
        due_reminder_stage(starts_at, "none", now=starts_at - timedelta(minutes=24))
        == "t_minus_24h"
    )
    assert due_reminder_stage(starts_at, "none", now=starts_at - timedelta(minutes=30)) is None


# --- process_due_meeting_reminders: fan-out across channels ---


def test_reminder_fans_out_across_every_verified_channel(db_session, org, monkeypatch):
    monkeypatch.setattr(config_module.settings, "nudge_time_scale", 1.0)
    organizer = _principal(db_session, org, id="p_organizer")
    attendee = _principal(
        db_session, org, id="p_attendee", channels=("discord", "telegram", "email")
    )
    starts_at = NOON
    meeting = schedule_meeting(
        db_session,
        org_id=org.id,
        organizer_principal_id=organizer.id,
        title="all hands",
        starts_at=starts_at,
        attendee_principal_ids=[attendee.id],
    )

    actions = process_due_meeting_reminders(db_session, now=starts_at - timedelta(hours=24))

    attendee_actions = [a for a in actions if a["principal_id"] == attendee.id]
    assert {a["channel"] for a in attendee_actions} == {"discord", "telegram", "email"}
    assert all(a["stage"] == "t_minus_24h" for a in attendee_actions)
    nudges = list_nudges(db_session, kind=NudgeKind.MEETING_REMINDER.value)
    assert len(nudges) == 3  # one per channel, for the attendee (organizer not due w/o binding)
    _ = meeting


def test_reminder_stages_progress_t24_t60_t10_across_ticks(db_session, org):
    organizer = _principal(db_session, org, id="p_organizer")
    attendee = _principal(db_session, org, id="p_attendee", channels=("discord",))
    starts_at = NOON
    schedule_meeting(
        db_session,
        org_id=org.id,
        organizer_principal_id=organizer.id,
        title="all hands",
        starts_at=starts_at,
        attendee_principal_ids=[attendee.id],
    )

    stages_seen = []
    for now in (
        starts_at - timedelta(hours=24),
        starts_at - timedelta(minutes=60),
        starts_at - timedelta(minutes=10),
    ):
        actions = process_due_meeting_reminders(db_session, now=now)
        stages_seen.extend(a["stage"] for a in actions if a["principal_id"] == attendee.id)

    assert stages_seen == ["t_minus_24h", "t_minus_60m", "t_minus_10m"]


def test_reminder_not_resent_within_same_stage(db_session, org):
    organizer = _principal(db_session, org, id="p_organizer")
    attendee = _principal(db_session, org, id="p_attendee", channels=("discord",))
    starts_at = NOON
    schedule_meeting(
        db_session,
        org_id=org.id,
        organizer_principal_id=organizer.id,
        title="all hands",
        starts_at=starts_at,
        attendee_principal_ids=[attendee.id],
    )

    first = process_due_meeting_reminders(db_session, now=starts_at - timedelta(hours=24))
    second = process_due_meeting_reminders(
        db_session, now=starts_at - timedelta(hours=23, minutes=59)
    )

    assert len(first) == 1
    assert second == []
