"""Meetings: scheduling, RSVP, slot finding, and scaled reminder fan-out."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from cerebro.clock.ladder import skip_quiet_hours
from cerebro.config import settings
from cerebro.db.models import (
    ChannelBinding,
    Meeting,
    MeetingAttendee,
    MeetingStatus,
    NudgeKind,
    RSVPStatus,
)
from cerebro.services import nudges as nudges_service

# Ordered farthest-to-nearest; index also encodes "already fired" progression.
REMINDER_STAGES: tuple[tuple[str, int], ...] = (
    ("t_minus_24h", 1440),
    ("t_minus_60m", 60),
    ("t_minus_10m", 10),
)
STAGE_ORDER: tuple[str, ...] = ("none", *[stage for stage, _ in REMINDER_STAGES])
STAGE_LABEL: dict[str, str] = {
    "t_minus_24h": "in 24 hours",
    "t_minus_60m": "in 60 minutes",
    "t_minus_10m": "in 10 minutes",
}


def serialize_meeting(meeting: Meeting) -> dict[str, Any]:
    """Serialize a Meeting row for tool/API responses."""
    return {
        "id": meeting.id,
        "org_id": meeting.org_id,
        "organizer_principal_id": meeting.organizer_principal_id,
        "title": meeting.title,
        "starts_at": meeting.starts_at.isoformat() if meeting.starts_at else "",
        "duration_minutes": meeting.duration_minutes,
        "status": meeting.status,
    }


def list_meetings(session: Session, *, principal_id: str) -> list[Meeting]:
    """List meetings where the principal organizes or attends, soonest first."""
    attendee_meeting_ids = session.query(MeetingAttendee.meeting_id).filter(
        MeetingAttendee.principal_id == principal_id
    )
    return (
        session.query(Meeting)
        .filter(
            or_(
                Meeting.organizer_principal_id == principal_id,
                Meeting.id.in_(attendee_meeting_ids),
            )
        )
        .order_by(Meeting.starts_at.asc())
        .all()
    )


def meeting_status(session: Session, *, meeting_id: str) -> dict[str, Any] | None:
    """Return a serialized meeting plus every attendee's RSVP status."""
    meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()
    if meeting is None:
        return None
    attendees = (
        session.query(MeetingAttendee).filter(MeetingAttendee.meeting_id == meeting_id).all()
    )
    data = serialize_meeting(meeting)
    data["attendees"] = [
        {"principal_id": attendee.principal_id, "rsvp_status": attendee.rsvp_status}
        for attendee in attendees
    ]
    return data


def schedule_meeting(
    session: Session,
    *,
    org_id: str,
    organizer_principal_id: str,
    title: str,
    starts_at: datetime,
    duration_minutes: int = 30,
    attendee_principal_ids: Sequence[str] = (),
) -> Meeting:
    """Create a meeting and its attendee rows (organizer included, RSVP pending)."""
    meeting = Meeting(
        id=str(uuid.uuid4()),
        org_id=org_id,
        organizer_principal_id=organizer_principal_id,
        title=title,
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        status=MeetingStatus.SCHEDULED.value,
        created_at=datetime.now(UTC),
    )
    session.add(meeting)
    session.flush()

    attendee_ids = {organizer_principal_id, *attendee_principal_ids}
    for principal_id in attendee_ids:
        session.add(
            MeetingAttendee(
                id=str(uuid.uuid4()),
                meeting_id=meeting.id,
                principal_id=principal_id,
                rsvp_status=RSVPStatus.PENDING.value,
                reminder_stage="none",
                created_at=datetime.now(UTC),
            )
        )
    session.commit()
    return meeting


def cancel_meeting(session: Session, *, meeting: Meeting) -> Meeting:
    """Cancel a meeting and notify every attendee."""
    meeting.status = MeetingStatus.CANCELLED.value
    session.flush()
    attendees = (
        session.query(MeetingAttendee).filter(MeetingAttendee.meeting_id == meeting.id).all()
    )
    for attendee in attendees:
        nudges_service.create_nudge(
            session,
            org_id=meeting.org_id,
            principal_id=attendee.principal_id,
            body=f"'{meeting.title}' has been cancelled.",
            kind=NudgeKind.MEETING_CANCELLED.value,
        )
    session.commit()
    return meeting


def rsvp(
    session: Session, *, meeting_id: str, principal_id: str, status: str
) -> MeetingAttendee | None:
    """Record an attendee's RSVP."""
    attendee = (
        session.query(MeetingAttendee)
        .filter(
            MeetingAttendee.meeting_id == meeting_id,
            MeetingAttendee.principal_id == principal_id,
        )
        .first()
    )
    if attendee is None:
        return None
    attendee.rsvp_status = status
    session.commit()
    return attendee


def _round_up_to_half_hour(moment: datetime) -> datetime:
    """Round a datetime up to the next :00 or :30 mark."""
    moment = moment.replace(second=0, microsecond=0)
    remainder = moment.minute % 30
    if remainder == 0:
        return moment
    return moment + timedelta(minutes=30 - remainder)


def find_slot(
    busy: Sequence[tuple[datetime, datetime]],
    *,
    duration_minutes: int,
    after: datetime,
) -> datetime:
    """Pure: earliest half-hour-aligned slot, avoiding busy intervals and quiet hours."""
    candidate = _round_up_to_half_hour(after)
    while True:
        candidate = skip_quiet_hours(candidate)
        candidate = _round_up_to_half_hour(candidate)
        candidate_end = candidate + timedelta(minutes=duration_minutes)
        conflict = next(
            (b for b in busy if b[0] < candidate_end and candidate < b[1]), None
        )
        if conflict is None:
            return candidate
        candidate = _round_up_to_half_hour(conflict[1])


def _as_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC-aware (SQLite often returns naive values)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def due_reminder_stage(
    starts_at: datetime, current_stage: str, *, now: datetime
) -> str | None:
    """Return the next un-fired reminder stage whose scaled threshold has passed."""
    remaining_minutes = (_as_utc(starts_at) - _as_utc(now)).total_seconds() / 60
    current_index = STAGE_ORDER.index(current_stage)
    for stage_name, base_minutes in REMINDER_STAGES:
        stage_index = STAGE_ORDER.index(stage_name)
        if stage_index <= current_index:
            continue
        threshold = base_minutes * settings.nudge_time_scale
        if remaining_minutes <= threshold:
            return stage_name
    return None


def process_due_meeting_reminders(
    session: Session, *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Fan out due reminders across every verified channel of each attendee."""
    moment = now or datetime.now(UTC)
    actions: list[dict[str, Any]] = []
    meetings = (
        session.query(Meeting)
        .filter(Meeting.status == MeetingStatus.SCHEDULED.value)
        .all()
    )
    for meeting in meetings:
        attendees = (
            session.query(MeetingAttendee)
            .filter(MeetingAttendee.meeting_id == meeting.id)
            .all()
        )
        for attendee in attendees:
            stage = due_reminder_stage(meeting.starts_at, attendee.reminder_stage, now=moment)
            if stage is None:
                continue
            bindings = (
                session.query(ChannelBinding)
                .filter(
                    ChannelBinding.principal_id == attendee.principal_id,
                    ChannelBinding.verified == "verified",
                )
                .all()
            )
            for binding in bindings:
                nudge = nudges_service.create_nudge(
                    session,
                    org_id=meeting.org_id,
                    principal_id=attendee.principal_id,
                    body=(
                        f"Reminder: '{meeting.title}' starts {STAGE_LABEL[stage]} "
                        f"(via {binding.channel})."
                    ),
                    kind=NudgeKind.MEETING_REMINDER.value,
                )
                actions.append(
                    {
                        "action": "reminder",
                        "meeting_id": meeting.id,
                        "principal_id": attendee.principal_id,
                        "channel": binding.channel,
                        "stage": stage,
                        "nudge_id": nudge.id,
                    }
                )
            attendee.reminder_stage = stage
    session.commit()
    return actions


def register_meeting_reminder_job(
    scheduler: Any, session_factory: Any, *, interval_seconds: float = 5.0
) -> str:
    """Attach the meeting reminder job to a Scheduler on a daemon thread."""

    def _tick() -> None:
        session = session_factory()
        try:
            process_due_meeting_reminders(session)
        finally:
            session.close()

    return scheduler.every(interval_seconds, _tick, name="meeting_reminders")
