"""Order intake job: auto-decompose, auto-assign, and raise a Jira ticket
for orders nobody has actioned yet - the automatic pipeline that used to
not exist (see the live-testing bug report: an order opened via Telegram
sat at "open", unassigned, with no ticket, until someone thought to call
decompose_order/assign_task/create_jira_ticket by hand). Same pattern as
gap_chase/task_ladder: a pure-ish core function plus a scheduler job that
ticks it on a daemon thread (see gateway.py)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.config import settings
from cerebro.db.models import Order, OrderStatus, Task
from cerebro.jira import api as jira_api
from cerebro.jira import auth as jira_auth
from cerebro.services import tasks as tasks_service
from cerebro.services.orders import dumps_fields, loads_fields

# Same keyword-pattern-matching idiom as orders_service.infer_order_type -
# order_type itself is free text (the model can and does invent values like
# "frontend_development"), so it can't be mapped to a designation with a
# fixed lookup table.
_DESIGNATION_KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "dev",
        re.compile(
            r"\b(dev|frontend|front-end|backend|back-end|bug|feature|code|api|"
            r"integration|build|app|software|website)\b",
            re.I,
        ),
    ),
    (
        "ops",
        re.compile(
            r"\b(ops|deploy|ci|infra|incident|outage|schedule|meeting|notify)\b",
            re.I,
        ),
    ),
)


def infer_designation(order_type: str, free_text: str) -> str:
    """Heuristic order_type/free_text -> team designation. Defaults to 'ops',
    the catch-all team population, when nothing matches, so every order
    lands on *someone's* queue rather than silently going undecomposed."""
    haystack = f"{order_type} {free_text or ''}"
    for designation, pattern in _DESIGNATION_KEYWORDS:
        if pattern.search(haystack):
            return designation
    return "ops"


def _undecomposed_open_orders(session: Session) -> list[Order]:
    """OPEN orders with zero tasks yet - the ones intake hasn't touched."""
    decomposed_order_ids = {
        row[0] for row in session.query(Task.order_id).filter(Task.order_id.isnot(None)).all()
    }
    orders = session.query(Order).filter(Order.status == OrderStatus.OPEN.value).all()
    return [o for o in orders if o.id not in decomposed_order_ids]


def _raise_jira_ticket(order: Order, *, client: jira_api.JiraAPI | None) -> str | None:
    """Best-effort: a missing/broken Jira config shouldn't block decomposition
    and assignment, so failures here are swallowed, not raised."""
    if not settings.jira_default_project_key:
        return None
    try:
        jira_client = client or jira_api.JiraAPI(jira_auth.JiraAuth())
        issue = jira_client.create_issue(
            settings.jira_default_project_key,
            summary=(order.free_text or order.order_type)[:250],
            description=order.free_text or "",
            issue_type="Task",
            labels=["cerebro-auto"],
        )
        return issue.get("key")
    except (jira_auth.JiraAuthError, jira_api.JiraAPIError):
        return None


def process_new_orders(
    session: Session,
    *,
    now: datetime | None = None,
    jira_client: jira_api.JiraAPI | None = None,
) -> list[dict[str, Any]]:
    """One intake tick: decompose, assign, and raise a ticket for every
    undecomposed OPEN order. Idempotent - an order is only touched once,
    the moment it gets its first Task row."""
    moment = now or datetime.now(UTC)
    actions: list[dict[str, Any]] = []

    for order in _undecomposed_open_orders(session):
        designation = infer_designation(order.order_type, order.free_text or "")
        created_tasks = tasks_service.decompose_order(session, order, designation=designation)

        assigned_numbers = []
        for task in created_tasks:
            assignee = tasks_service.assign_task(session, task)
            if assignee is not None:
                tasks_service.send_task_card(session, task)
                assigned_numbers.append(task.number)

        jira_key = _raise_jira_ticket(order, client=jira_client)
        if jira_key:
            fields = loads_fields(order.fields_json)
            fields["jira_key"] = jira_key
            order.fields_json = dumps_fields(fields)

        order.status = OrderStatus.IN_PROGRESS.value
        order.updated_at = moment
        session.commit()

        actions.append(
            {
                "action": "order_decomposed",
                "order_id": order.id,
                "designation": designation,
                "task_numbers": [t.number for t in created_tasks],
                "assigned_task_numbers": assigned_numbers,
                "jira_key": jira_key,
            }
        )

    return actions


def register_order_intake_job(
    scheduler: Any, session_factory: Any, *, interval_seconds: float = 5.0
) -> str:
    """Attach the order intake job to a Scheduler on a daemon thread."""

    def _tick() -> None:
        session = session_factory()
        try:
            process_new_orders(session)
        finally:
            session.close()

    return scheduler.every(interval_seconds, _tick, name="order_intake")
