"""Orders ledger service."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Order, OrderStatus, Principal

_ORDER_TYPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("schedule", re.compile(r"\b(schedule|meeting|call|sync)\b", re.I)),
    ("notify", re.compile(r"\b(notify|tell|ping|alert)\b", re.I)),
    ("summary", re.compile(r"\b(summary|summarize|decide|decision)\b", re.I)),
    ("ci", re.compile(r"\b(deploy|ci|workflow|rerun)\b", re.I)),
)


def infer_order_type(text: str) -> str:
    """Infer an order_type label from free text."""
    for order_type, pattern in _ORDER_TYPE_PATTERNS:
        if pattern.search(text):
            return order_type
    return "general"


def loads_fields(raw: str | None) -> dict[str, Any]:
    """Parse an order fields_json payload into a dict."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def dumps_fields(fields: dict[str, Any]) -> str:
    """Serialize order fields to JSON text."""
    return json.dumps(fields)


def serialize_order(order: Order) -> dict[str, Any]:
    """Serialize an Order row for tool/API responses."""
    return {
        "id": order.id,
        "org_id": order.org_id,
        "principal_id": order.principal_id,
        "order_type": order.order_type,
        "status": order.status,
        "free_text": order.free_text or "",
        "fields": loads_fields(order.fields_json),
        "created_at": order.created_at.isoformat() if order.created_at else "",
        "updated_at": order.updated_at.isoformat() if order.updated_at else "",
    }


def open_order(
    session: Session,
    *,
    principal: Principal,
    text: str = "",
    order_type: str | None = None,
    fields: dict[str, Any] | None = None,
) -> Order:
    """Open an order from free text and/or an explicit order_type."""
    free_text = (text or "").strip()
    resolved_type = (order_type or "").strip() or (
        infer_order_type(free_text) if free_text else "general"
    )
    now = datetime.now(UTC)
    order = Order(
        id=str(uuid.uuid4()),
        org_id=principal.org_id,
        principal_id=principal.id,
        order_type=resolved_type,
        status=OrderStatus.OPEN.value,
        free_text=free_text or None,
        fields_json=dumps_fields(fields or {}),
        created_at=now,
        updated_at=now,
    )
    session.add(order)
    session.commit()
    return order


def update_order_fields(
    session: Session,
    *,
    order_id: str,
    fields: dict[str, Any],
    principal: Principal | None = None,
) -> Order | None:
    """Merge fields into an existing order and touch updated_at."""
    order = session.query(Order).filter(Order.id == order_id).first()
    if order is None:
        return None
    if principal is not None and order.principal_id != principal.id:
        if principal.population.value == "client":
            return None
    merged = loads_fields(order.fields_json)
    merged.update(fields)
    order.fields_json = dumps_fields(merged)
    order.updated_at = datetime.now(UTC)
    if order.status == OrderStatus.OPEN.value:
        order.status = OrderStatus.IN_PROGRESS.value
    session.commit()
    return order


def order_status(session: Session, *, order_id: str) -> dict[str, Any] | None:
    """Return a serialized order by id."""
    order = session.query(Order).filter(Order.id == order_id).first()
    if order is None:
        return None
    return serialize_order(order)


def list_orders(
    session: Session,
    *,
    principal: Principal,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List orders for the caller's org, newest first."""
    query = session.query(Order).filter(Order.org_id == principal.org_id)
    if principal.population.value == "client":
        query = query.filter(Order.principal_id == principal.id)
    if status:
        query = query.filter(Order.status == status)
    orders = query.order_by(Order.created_at.desc()).limit(max(1, min(limit, 100))).all()
    return [serialize_order(order) for order in orders]
