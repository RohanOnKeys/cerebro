"""Task decomposition, assignment, ACK/BLOCKED transitions, and the ladder job."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence

from sqlalchemy.orm import Session

from cerebro.clock import ladder
from cerebro.db.models import (
    ChannelBinding,
    LadderStatus,
    NudgeKind,
    Order,
    Principal,
    Task,
    TaskStatus,
)
from cerebro.services import nudges as nudges_service

DEFAULT_WIP_CAP = 3


def loads_skills(raw: str | None) -> list[str]:
    """Parse a skills_json payload into a list."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return list(data) if isinstance(data, list) else []


def dumps_skills(skills: Sequence[str]) -> str:
    """Serialize a skills list to JSON text."""
    return json.dumps(list(skills))


def serialize_task(task: Task) -> dict[str, Any]:
    """Serialize a Task row for tool/API responses."""
    return {
        "id": task.id,
        "number": task.number,
        "org_id": task.org_id,
        "order_id": task.order_id,
        "title": task.title,
        "description": task.description or "",
        "designation": task.designation,
        "required_skills": loads_skills(task.required_skills_json),
        "status": task.status,
        "assignee_principal_id": task.assignee_principal_id,
        "blocked_reason": task.blocked_reason or "",
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "updated_at": task.updated_at.isoformat() if task.updated_at else "",
    }


def next_task_number(session: Session, org_id: str) -> int:
    """Return the next per-org human-facing task number."""
    current_max = (
        session.query(Task.number)
        .filter(Task.org_id == org_id)
        .order_by(Task.number.desc())
        .limit(1)
        .scalar()
    )
    return (current_max or 0) + 1


def decompose_order_text(free_text: str, order_type: str) -> list[str]:
    """Pure: split free text into candidate task titles."""
    text = (free_text or "").strip()
    if not text:
        return [f"{order_type} task"]
    parts = re.split(r"\n+|;|(?:\band\b)", text, flags=re.I)
    titles = [part.strip(" -*\t") for part in parts if part.strip(" -*\t")]
    return titles or [text]


def create_task(
    session: Session,
    *,
    org_id: str,
    title: str,
    designation: str,
    order_id: str | None = None,
    description: str | None = None,
    required_skills: Sequence[str] | None = None,
) -> Task:
    """Persist a new task row."""
    now = datetime.now(UTC)
    task = Task(
        id=str(uuid.uuid4()),
        org_id=org_id,
        order_id=order_id,
        number=next_task_number(session, org_id),
        title=title,
        description=description,
        designation=designation,
        required_skills_json=dumps_skills(required_skills or []),
        status=TaskStatus.OPEN.value,
        ladder_rung=0,
        ladder_status=LadderStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.commit()
    return task


def decompose_order(
    session: Session,
    order: Order,
    *,
    designation: str,
    required_skills: Sequence[str] | None = None,
) -> list[Task]:
    """Split an order into one or more tasks and persist them."""
    titles = decompose_order_text(order.free_text or "", order.order_type)
    return [
        create_task(
            session,
            org_id=order.org_id,
            order_id=order.id,
            title=title,
            designation=designation,
            required_skills=required_skills,
        )
        for title in titles
    ]


@dataclass(frozen=True)
class CandidateView:
    """Lightweight assignment candidate used by the pure filter chain."""

    principal_id: str
    population: str
    skills: frozenset[str]
    wip_cap: int
    current_load: int


def select_assignee(
    candidates: Sequence[CandidateView],
    *,
    designation: str,
    required_skills: Sequence[str] = (),
) -> str | None:
    """Pure filter chain: designation, then skills, then wip_cap, then lowest load."""
    by_designation = [c for c in candidates if c.population == designation]
    if not by_designation:
        return None

    required = set(required_skills)
    by_skills = [c for c in by_designation if required.issubset(c.skills)]
    if not by_skills:
        return None

    under_cap = [c for c in by_skills if c.current_load < c.wip_cap]
    if not under_cap:
        return None

    under_cap.sort(key=lambda c: (c.current_load, c.principal_id))
    return under_cap[0].principal_id


def _current_load(session: Session, principal_id: str) -> int:
    return (
        session.query(Task)
        .filter(
            Task.assignee_principal_id == principal_id,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.ACKED.value]),
        )
        .count()
    )


def assign_task(session: Session, task: Task) -> Principal | None:
    """Assign an open task to a principal via the designation/skills/wip_cap chain."""
    candidates = (
        session.query(Principal)
        .filter(Principal.org_id == task.org_id, Principal.population == task.designation)
        .all()
    )
    views = [
        CandidateView(
            principal_id=principal.id,
            population=principal.population.value
            if hasattr(principal.population, "value")
            else principal.population,
            skills=frozenset(loads_skills(principal.skills_json)),
            wip_cap=principal.wip_cap or DEFAULT_WIP_CAP,
            current_load=_current_load(session, principal.id),
        )
        for principal in candidates
    ]
    chosen_id = select_assignee(
        views,
        designation=task.designation,
        required_skills=loads_skills(task.required_skills_json),
    )
    if chosen_id is None:
        return None

    chosen = next(p for p in candidates if p.id == chosen_id)
    task.assignee_principal_id = chosen.id
    task.updated_at = datetime.now(UTC)
    session.commit()
    return chosen


def send_task_card(session: Session, task: Task) -> nudges_service.Nudge:
    """Fan out a task card to the assignee and arm rung 0 of the ladder."""
    now = datetime.now(UTC)
    body = (
        f"New task {task.number}: {task.title}. "
        f"Reply ACK {task.number} to accept, or BLOCKED {task.number} <reason>."
    )
    nudge = nudges_service.create_nudge(
        session,
        org_id=task.org_id,
        principal_id=task.assignee_principal_id,
        order_id=task.order_id,
        body=body,
        kind=NudgeKind.TASK_CARD.value,
    )
    advanced = ladder.advance(
        ladder.LadderView(rung=task.ladder_rung, status=task.ladder_status), now=now
    )
    task.ladder_rung = advanced.rung
    task.ladder_last_fired_at = advanced.last_fired_at
    task.ladder_next_due_at = advanced.next_due_at
    task.ladder_status = advanced.status
    task.updated_at = now
    session.commit()
    return nudge


def get_task_by_number(session: Session, *, org_id: str, number: int) -> Task | None:
    """Look up a task by its per-org human-facing number."""
    return (
        session.query(Task).filter(Task.org_id == org_id, Task.number == number).first()
    )


def ack_task(session: Session, *, org_id: str, number: int) -> Task | None:
    """Acknowledge a task: cancels remaining ladder rungs."""
    task = get_task_by_number(session, org_id=org_id, number=number)
    if task is None:
        return None
    now = datetime.now(UTC)
    task.status = TaskStatus.ACKED.value
    task.acked_at = now
    task.updated_at = now
    cancelled = ladder.cancel(
        ladder.LadderView(rung=task.ladder_rung, status=task.ladder_status)
    )
    task.ladder_status = cancelled.status
    task.ladder_next_due_at = cancelled.next_due_at
    session.commit()
    return task


def block_task(
    session: Session, *, org_id: str, number: int, principal: Principal, reason: str
) -> Task | None:
    """Mark a task blocked and notify the org's leads."""
    task = get_task_by_number(session, org_id=org_id, number=number)
    if task is None:
        return None
    now = datetime.now(UTC)
    task.status = TaskStatus.BLOCKED.value
    task.blocked_reason = reason or "no reason given"
    task.updated_at = now
    session.commit()

    leads = (
        session.query(Principal)
        .filter(Principal.org_id == org_id, Principal.population == "lead")
        .all()
    )
    for lead in leads:
        nudges_service.create_nudge(
            session,
            org_id=org_id,
            principal_id=lead.id,
            order_id=task.order_id,
            body=(
                f"Task {task.number} ({task.title}) blocked by {principal.id}: "
                f"{task.blocked_reason}"
            ),
            kind=NudgeKind.TASK_BLOCKED.value,
        )
    return task


def list_tasks_for_principal(session: Session, *, principal: Principal) -> list[Task]:
    """List tasks assigned to a principal, newest first."""
    return (
        session.query(Task)
        .filter(Task.assignee_principal_id == principal.id)
        .order_by(Task.created_at.desc())
        .all()
    )


def process_due_task_ladders(
    session: Session, *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Run one ladder tick: coalesce due rungs per assignee, respecting rate caps."""
    moment = now or datetime.now(UTC)
    active_tasks = (
        session.query(Task)
        .filter(
            Task.ladder_status == LadderStatus.ACTIVE.value,
            Task.status == TaskStatus.OPEN.value,
            Task.assignee_principal_id.isnot(None),
        )
        .all()
    )

    due_by_task: dict[str, Task] = {}
    due_views: list[ladder.DueTask] = []
    for task in active_tasks:
        view = ladder.LadderView(
            rung=task.ladder_rung,
            last_fired_at=task.ladder_last_fired_at,
            next_due_at=task.ladder_next_due_at,
            status=task.ladder_status,
        )
        if ladder.due(view, now=moment):
            due_by_task[task.id] = task
            due_views.append(
                ladder.DueTask(
                    task_id=task.id,
                    number=task.number,
                    title=task.title,
                    assignee_principal_id=task.assignee_principal_id,
                )
            )

    actions: list[dict[str, Any]] = []
    grouped = ladder.group_due_by_assignee(due_views)
    for principal_id, tasks_due in grouped.items():
        reachable = (
            session.query(ChannelBinding)
            .filter(
                ChannelBinding.principal_id == principal_id,
                ChannelBinding.verified == "verified",
            )
            .first()
            is not None
        )
        if not reachable:
            continue

        last_nudge = (
            session.query(nudges_service.Nudge)
            .filter(
                nudges_service.Nudge.principal_id == principal_id,
                nudges_service.Nudge.kind == NudgeKind.TASK_LADDER.value,
            )
            .order_by(nudges_service.Nudge.created_at.desc())
            .first()
        )
        last_fired_at = last_nudge.created_at if last_nudge else None
        if not ladder.allowed_by_rate_cap(last_fired_at, now=moment):
            continue

        org_id = due_by_task[tasks_due[0].task_id].org_id
        nudge = nudges_service.create_nudge(
            session,
            org_id=org_id,
            principal_id=principal_id,
            body=ladder.coalesced_body(tasks_due),
            kind=NudgeKind.TASK_LADDER.value,
        )
        actions.append(
            {
                "action": "ladder_nudge",
                "principal_id": principal_id,
                "task_numbers": [t.number for t in tasks_due],
                "nudge_id": nudge.id,
            }
        )

        for due_task in tasks_due:
            task = due_by_task[due_task.task_id]
            view = ladder.LadderView(
                rung=task.ladder_rung,
                last_fired_at=task.ladder_last_fired_at,
                next_due_at=task.ladder_next_due_at,
                status=task.ladder_status,
            )
            advanced = ladder.advance(view, now=moment)
            task.ladder_rung = advanced.rung
            task.ladder_last_fired_at = advanced.last_fired_at
            task.ladder_next_due_at = advanced.next_due_at
            task.ladder_status = advanced.status
            task.updated_at = moment

    session.commit()
    return actions


def register_task_ladder_job(
    scheduler: Any, session_factory: Any, *, interval_seconds: float = 5.0
) -> str:
    """Attach the task ladder job to a Scheduler on a daemon thread."""

    def _tick() -> None:
        session = session_factory()
        try:
            process_due_task_ladders(session)
        finally:
            session.close()

    return scheduler.every(interval_seconds, _tick, name="task_ladder")
