"""Challenge minting: nonces, TTLs, and action hashes."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Approval, ApprovalState, Principal

# Unambiguous alphabet: no 0/O, 1/I/L (human-transcription safe).
NONCE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
DEFAULT_NONCE_LENGTH = 8
DEFAULT_TTL = timedelta(minutes=10)


def mint_nonce(length: int = DEFAULT_NONCE_LENGTH) -> str:
    """Mint a nonce using the unambiguous alphabet."""
    return "".join(secrets.choice(NONCE_ALPHABET) for _ in range(length))


def nonce_alphabet_ok(nonce: str) -> bool:
    """Return True when every character is in the unambiguous alphabet."""
    if not nonce:
        return False
    return all(ch in NONCE_ALPHABET for ch in nonce)


def compute_action_hash(action: str, args: dict[str, Any]) -> str:
    """Hash action name plus canonical args for tamper detection."""
    payload = {"action": action, "args": args}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mint_challenge(
    session: Session,
    *,
    principal: Principal,
    action: str,
    args: dict[str, Any] | None = None,
    channel: str = "",
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> Approval:
    """Persist a pending Approval challenge with nonce, TTL, and action_hash."""
    moment = now or datetime.now(UTC)
    tool_args = dict(args or {})
    action_hash = compute_action_hash(action, tool_args)
    payload: dict[str, Any] = {"args": tool_args, "action_hash": action_hash}
    if channel:
        payload["channel"] = channel
    approval = Approval(
        id=str(uuid.uuid4()),
        org_id=principal.org_id,
        principal_id=principal.id,
        nonce=mint_nonce(),
        state=ApprovalState.PENDING.value,
        action=action,
        payload_json=json.dumps(payload, sort_keys=True),
        expires_at=moment + ttl,
        created_at=moment,
    )
    session.add(approval)
    session.commit()
    return approval


def write_refusal_audit(
    session: Session,
    *,
    principal: Principal,
    reason: str,
    action: str,
    details: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Approval:
    """Persist a denied Approval row documenting a verification refusal."""
    moment = now or datetime.now(UTC)
    payload = {"refusal_reason": reason, **(details or {})}
    approval = Approval(
        id=str(uuid.uuid4()),
        org_id=principal.org_id,
        principal_id=principal.id,
        nonce=mint_nonce(),
        state=ApprovalState.DENIED.value,
        action=f"refusal.{reason}",
        payload_json=json.dumps(payload, sort_keys=True),
        expires_at=moment,
        created_at=moment,
        resolved_at=moment,
    )
    session.add(approval)
    session.commit()
    return approval


def load_payload(approval: Approval) -> dict[str, Any]:
    """Parse an approval payload_json blob."""
    try:
        data = json.loads(approval.payload_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def stored_action_hash(approval: Approval) -> str:
    """Return the action_hash embedded in the approval payload."""
    return str(load_payload(approval).get("action_hash") or "")


def stored_args(approval: Approval) -> dict[str, Any]:
    """Return the args embedded in the approval payload."""
    args = load_payload(approval).get("args") or {}
    return dict(args) if isinstance(args, dict) else {}


def stored_channel(approval: Approval) -> str:
    """Return the channel sealed when the challenge was minted."""
    return str(load_payload(approval).get("channel") or "")
