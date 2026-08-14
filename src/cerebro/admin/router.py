"""Admin/Read API for the Cerebro team dashboard.

Everything here is READ-ONLY (plain SELECTs, no writes) and sits behind the
`require_admin_token` dependency (see cerebro.admin.auth) — every route in
this router requires a valid bearer token before touching the database.

Response shapes are written to match cerebro-web/src/lib/types.ts exactly,
field for field, so the frontend needs zero mapping/transform logic beyond
calling `.json()`.

Honest limitations, by endpoint (see the accompanying guide for the full
explanation of each):

- /admin/channels: "live" vs "reconnect_needed" is a heuristic (most recent
  Message.created_at per channel, compared to a staleness threshold), not a
  real webhook health check. There is no channel-heartbeat table yet.
- /admin/projects: NOT backed by the database. There is no Project/Phase
  table in the schema — this is roadmap/planning content, not operational
  data, so it's served from the static PROJECTS constant below. Edit that
  constant by hand when the roadmap changes; do not expect this endpoint to
  reflect a live thing.
- /admin/approvals/pending: RoleClaim rows awaiting peer approval
  (see enrollment role gate), shaped as PendingApproval for the dashboard.
- /admin/members: `name` falls back to `email` when Principal.display_name
  is null (see migration 0015) — nothing backfills display_name today.
- /admin/meetings: uses existing Meeting.provider / Meeting.join_url
  (added in 0014_role_claims_and_meeting_providers).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from cerebro.admin.auth import require_admin_token
from cerebro.db.models import (
    ChannelBinding,
    CiRun,
    Crossing,
    Meeting,
    MeetingAttendee,
    Message,
    Principal,
    RoleClaim,
    RoleClaimStatus,
)
from cerebro.db.session import get_session
from cerebro.registry import TOOLS

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)

# How stale a channel's last message can be before the dashboard shows
# "Reconnect needed" instead of "Live". Tune per how chatty each org is.
CHANNEL_STALE_AFTER = timedelta(hours=12)

KNOWN_CHANNELS = ("telegram", "discord", "slack", "email")

# Not backed by the database — see module docstring. Edit by hand.
PROJECTS: list[dict[str, str]] = [
    {
        "id": "proj-tasks-meetings",
        "name": "Tasks and meetings",
        "phase": "Phase 4",
        "status": "in_review",
        "owner": "Core team",
        "note": "Assignment filter chain and unacked ladder under review.",
    },
    {
        "id": "proj-membrane-identity",
        "name": "Membrane and identity",
        "phase": "Phase 5",
        "status": "in_review",
        "owner": "Core team",
        "note": "Crossing policy rules being finalized.",
    },
    {
        "id": "proj-phase-8-freeze",
        "name": "Phase 8 freeze",
        "phase": "Phase 8",
        "status": "done",
        "owner": "Core team",
        "note": "WhatsApp cut and role approval gate.",
    },
]


def _session() -> Session:
    return get_session()


def _as_utc(value: datetime | None) -> datetime | None:
    """Every DateTime column in db/models.py is naive (no timezone=True),
    but every write path stores `datetime.now(UTC)` — so a naive value read
    back from the DB is UTC, it just lost its tzinfo in the round trip.
    Reattach it before comparing against or formatting alongside any
    timezone-aware datetime, or Python raises TypeError on comparison and
    the frontend gets an ambiguous timestamp with no offset."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    utc_value = _as_utc(value)
    return utc_value.isoformat() if utc_value is not None else None


def _naive_utc_now() -> datetime:
    """`datetime.now(UTC)` with tzinfo stripped, for comparing against the
    naive DateTime columns in a WHERE clause (see _as_utc above)."""
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """Powers the dashboard's top stat strip."""
    session = _session()
    try:
        members_count = session.scalar(select(func.count(Principal.id))) or 0

        pending_approvals_count = (
            session.scalar(
                select(func.count(RoleClaim.id)).where(
                    RoleClaim.status == RoleClaimStatus.PENDING.value
                )
            )
            or 0
        )

        since = _naive_utc_now() - timedelta(days=7)
        ci_runs_week = (
            session.scalar(select(func.count(CiRun.id)).where(CiRun.created_at >= since))
            or 0
        )

        today_start = _naive_utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        meetings_today = (
            session.scalar(
                select(func.count(Meeting.id)).where(
                    Meeting.starts_at >= today_start,
                    Meeting.starts_at < today_end,
                )
            )
            or 0
        )

        return {
            "items": [
                {"value": len(KNOWN_CHANNELS), "label": "Channels connected"},
                {"value": members_count, "label": "Members"},
                {"value": pending_approvals_count, "label": "Pending approvals"},
                {"value": ci_runs_week, "label": "CI runs this week"},
                {"value": meetings_today, "label": "Meetings today"},
            ]
        }
    finally:
        session.close()


@router.get("/channels")
def get_channels() -> dict[str, Any]:
    """Channel status. See module docstring: 'live' is a staleness heuristic,
    not a real webhook health check — there's no heartbeat table yet."""
    session = _session()
    try:
        cutoff = _naive_utc_now() - CHANNEL_STALE_AFTER
        rows = session.execute(
            select(
                Message.channel,
                func.max(Message.created_at).label("last_message_at"),
                func.count(Message.id).label("messages_today"),
            )
            .where(Message.created_at >= _naive_utc_now().replace(hour=0, minute=0, second=0, microsecond=0))
            .group_by(Message.channel)
        ).all()
        by_channel = {row.channel: row for row in rows}

        # Fold in the true last-message time (not just today's) for the
        # "last verified" timestamp, since a channel silent today but
        # active yesterday should still say when it was last seen.
        last_seen_rows = session.execute(
            select(Message.channel, func.max(Message.created_at)).group_by(Message.channel)
        ).all()
        last_seen = {channel: ts for channel, ts in last_seen_rows}

        result = []
        for channel in KNOWN_CHANNELS:
            last_at = last_seen.get(channel)
            today_row = by_channel.get(channel)
            state = "live" if last_at and last_at >= cutoff else "reconnect_needed"
            result.append(
                {
                    "channel": channel,
                    "state": state,
                    "lastVerifiedMessageAt": _iso(last_at),
                    "messagesToday": today_row.messages_today if today_row else 0,
                }
            )
        return {"items": result}
    finally:
        session.close()


@router.get("/projects")
def get_projects() -> dict[str, Any]:
    """Static roadmap content — see module docstring. Not a DB query."""
    return {"items": PROJECTS, "source": "static"}


@router.get("/members")
def get_members(limit: int = Query(default=100, le=500)) -> dict[str, Any]:
    session = _session()
    try:
        binding_counts = dict(
            session.execute(
                select(ChannelBinding.principal_id, func.count(ChannelBinding.id)).group_by(
                    ChannelBinding.principal_id
                )
            ).all()
        )
        principals = session.scalars(
            select(Principal).order_by(Principal.created_at.desc()).limit(limit)
        ).all()
        return {
            "items": [
                {
                    "id": p.id,
                    "name": p.display_name or p.email or p.id,
                    "population": p.population.value,
                    "channelBindingCount": binding_counts.get(p.id, 0),
                    "joinedAt": _iso(p.created_at),
                }
                for p in principals
            ]
        }
    finally:
        session.close()


@router.get("/approvals/pending")
def get_pending_approvals(limit: int = Query(default=50, le=200)) -> dict[str, Any]:
    """Pending RoleClaim rows shaped for the dashboard PendingApproval panel."""
    session = _session()
    try:
        rows = session.scalars(
            select(RoleClaim)
            .where(RoleClaim.status == RoleClaimStatus.PENDING.value)
            .order_by(RoleClaim.created_at.desc())
            .limit(limit)
        ).all()
        principal_ids = {row.claimant_principal_id for row in rows} | {
            row.approver_principal_id for row in rows if row.approver_principal_id
        }
        principals = {
            p.id: p
            for p in session.scalars(
                select(Principal).where(Principal.id.in_(principal_ids))
            ).all()
        } if principal_ids else {}
        return {
            "items": [
                {
                    "id": row.id,
                    "name": (
                        principals[row.claimant_principal_id].display_name
                        or principals[row.claimant_principal_id].email
                        or row.claimant_principal_id
                        if row.claimant_principal_id in principals
                        else row.claimant_principal_id
                    ),
                    "claimedRole": row.requested_population,
                    "eligibleApprover": (
                        principals[row.approver_principal_id].display_name
                        or principals[row.approver_principal_id].email
                        or row.approver_principal_id
                        if row.approver_principal_id
                        and row.approver_principal_id in principals
                        else "any peer in role"
                    ),
                }
                for row in rows
            ]
        }
    finally:
        session.close()


@router.get("/meetings")
def get_meetings(limit: int = Query(default=50, le=200)) -> dict[str, Any]:
    session = _session()
    try:
        now = _naive_utc_now()
        meetings = session.scalars(
            select(Meeting)
            .where(Meeting.starts_at >= now, Meeting.status != "cancelled")
            .order_by(Meeting.starts_at.asc())
            .limit(limit)
        ).all()
        meeting_ids = [m.id for m in meetings]

        attendee_rows = session.execute(
            select(
                MeetingAttendee.meeting_id,
                func.count(MeetingAttendee.id).label("total"),
                func.sum(
                    case((MeetingAttendee.rsvp_status == "yes", 1), else_=0)
                ).label("confirmed"),
            )
            .where(MeetingAttendee.meeting_id.in_(meeting_ids))
            .group_by(MeetingAttendee.meeting_id)
        ).all() if meeting_ids else []
        attendee_by_meeting = {row.meeting_id: row for row in attendee_rows}

        organizer_ids = {m.organizer_principal_id for m in meetings}
        organizers = {
            p.id: p
            for p in session.scalars(
                select(Principal).where(Principal.id.in_(organizer_ids))
            ).all()
        } if organizer_ids else {}

        items = []
        for m in meetings:
            attendee_info = attendee_by_meeting.get(m.id)
            organizer = organizers.get(m.organizer_principal_id)
            items.append(
                {
                    "id": m.id,
                    "title": m.title,
                    "startsAt": _iso(m.starts_at),
                    "organizer": (
                        (organizer.display_name or organizer.email or m.organizer_principal_id)
                        if organizer
                        else m.organizer_principal_id
                    ),
                    "provider": m.provider or None,
                    "joinUrl": m.join_url,
                    "attendeesConfirmed": int(attendee_info.confirmed or 0) if attendee_info else 0,
                    "attendeesTotal": int(attendee_info.total or 0) if attendee_info else 0,
                }
            )
        return {"items": items}
    finally:
        session.close()


@router.get("/reminders")
def get_reminders(limit: int = Query(default=100, le=500)) -> dict[str, Any]:
    """Scheduled reminders — derived from MeetingAttendee.reminder_stage,
    which the clock/scheduler.py meeting-reminder job already writes to."""
    session = _session()
    try:
        rows = session.execute(
            select(MeetingAttendee, Meeting.title)
            .join(Meeting, Meeting.id == MeetingAttendee.meeting_id)
            .where(MeetingAttendee.reminder_stage != "none")
            .where(Meeting.starts_at >= _naive_utc_now())
            .order_by(Meeting.starts_at.asc())
            .limit(limit)
        ).all()
        return {
            "items": [
                {
                    "id": attendee.id,
                    "meetingId": attendee.meeting_id,
                    "meetingTitle": title,
                    "stage": attendee.reminder_stage,
                }
                for attendee, title in rows
            ]
        }
    finally:
        session.close()


@router.get("/ci-runs")
def get_ci_runs(limit: int = Query(default=50, le=200)) -> dict[str, Any]:
    session = _session()
    try:
        rows = session.scalars(
            select(CiRun).order_by(CiRun.updated_at.desc()).limit(limit)
        ).all()
        principal_ids = {r.requested_by_principal_id for r in rows if r.requested_by_principal_id}
        principals = {
            p.id: p
            for p in session.scalars(
                select(Principal).where(Principal.id.in_(principal_ids))
            ).all()
        } if principal_ids else {}

        def result_label(run: CiRun) -> str:
            if run.status != "completed":
                return run.status or "in_progress"
            return run.conclusion or "unknown"

        items = []
        for run in rows:
            requester = principals.get(run.requested_by_principal_id) if run.requested_by_principal_id else None
            duration = (run.updated_at - run.created_at).total_seconds()
            items.append(
                {
                    "id": run.id,
                    "repo": run.repo,
                    "workflowName": run.workflow_name,
                    "triggeredBy": (
                        (requester.display_name or requester.email or run.requested_by_principal_id)
                        if requester
                        else "webhook"
                    ),
                    "result": result_label(run),
                    "durationSeconds": max(int(duration), 0),
                    "finishedAt": _iso(run.updated_at),
                }
            )
        return {"items": items}
    finally:
        session.close()


@router.get("/ledger")
def get_ledger(limit: int = Query(default=100, le=500)) -> dict[str, Any]:
    """Audit trail — backed by the crossings table (see membrane/policy.py
    and the developer guide's membrane section). Every population-crossing
    action is written here before the relay is attempted."""
    session = _session()
    try:
        rows = session.scalars(
            select(Crossing).order_by(Crossing.created_at.desc()).limit(limit)
        ).all()
        principal_ids = {r.principal_id for r in rows}
        principals = {
            p.id: p
            for p in session.scalars(
                select(Principal).where(Principal.id.in_(principal_ids))
            ).all()
        } if principal_ids else {}

        items = []
        for row in rows:
            principal = principals.get(row.principal_id)
            items.append(
                {
                    "id": row.id,
                    "principal": (
                        (principal.display_name or principal.email or row.principal_id)
                        if principal
                        else row.principal_id
                    ),
                    "action": f"{row.action} ({row.source_population} -> {row.target_population})",
                    "result": row.status,
                    "at": _iso(row.created_at),
                }
            )
        return {"items": items}
    finally:
        session.close()


@router.get("/allowlist")
def get_allowlist() -> dict[str, Any]:
    """Derived directly from registry.TOOLS — this is the actual,
    always-in-sync permission surface, not a manually maintained list."""
    rows = []
    for tool in sorted(TOOLS.values(), key=lambda t: t.name):
        rows.append(
            {
                "tool": tool.name,
                "populations": {
                    population.value: True
                    for population in tool.allowed_populations
                    if population.value != "client"
                },
            }
        )
    return {"items": rows}
