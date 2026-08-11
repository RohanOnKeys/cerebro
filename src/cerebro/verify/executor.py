"""Tier-gated tool executor with CONFIRM/DENY challenge handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import Approval, ApprovalState, Principal
from cerebro.registry import TOOLS, ToolSpec
from cerebro.verify.challenge import (
    compute_action_hash,
    mint_challenge,
    nonce_alphabet_ok,
    stored_action_hash,
    stored_args,
)


class ChallengeRejected(ValueError):
    """Raised when a CONFIRM/DENY challenge fails a predicate."""


@dataclass(frozen=True)
class PredicateResult:
    """Outcome of one verification predicate."""

    name: str
    ok: bool
    detail: str = ""


def predicate_alphabet(nonce: str) -> PredicateResult:
    """Nonce must use the unambiguous alphabet only."""
    ok = nonce_alphabet_ok(nonce)
    return PredicateResult("alphabet", ok, "" if ok else "nonce has ambiguous characters")


def predicate_exists(approval: Approval | None) -> PredicateResult:
    """Approval row must exist for the nonce."""
    ok = approval is not None
    return PredicateResult("exists", ok, "" if ok else "unknown nonce")


def predicate_pending(approval: Approval) -> PredicateResult:
    """Approval must still be pending (blocks replay)."""
    ok = approval.state == ApprovalState.PENDING.value
    return PredicateResult("pending", ok, "" if ok else f"state is {approval.state}")


def predicate_not_expired(
    approval: Approval, *, now: datetime | None = None
) -> PredicateResult:
    """Approval must not be past expires_at."""
    moment = now or datetime.now(UTC)
    expires = approval.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    ok = expires is not None and moment < expires
    return PredicateResult("not_expired", ok, "" if ok else "challenge expired")


def predicate_principal(
    approval: Approval, principal: Principal
) -> PredicateResult:
    """Confirming principal must own the challenge."""
    ok = approval.principal_id == principal.id
    return PredicateResult("principal", ok, "" if ok else "principal mismatch")


def predicate_action_hash(
    approval: Approval, *, action: str, args: dict[str, Any]
) -> PredicateResult:
    """Args/action must match the hash sealed at mint time."""
    expected = stored_action_hash(approval)
    actual = compute_action_hash(action, args)
    ok = bool(expected) and expected == actual
    return PredicateResult("action_hash", ok, "" if ok else "action hash mismatch")


def evaluate_predicates(
    approval: Approval | None,
    *,
    nonce: str,
    principal: Principal,
    action: str | None = None,
    args: dict[str, Any] | None = None,
    now: datetime | None = None,
    require_hash: bool = True,
) -> list[PredicateResult]:
    """Run the six challenge predicates in order."""
    results = [predicate_alphabet(nonce), predicate_exists(approval)]
    if approval is None:
        return results

    results.append(predicate_pending(approval))
    results.append(predicate_not_expired(approval, now=now))
    results.append(predicate_principal(approval, principal))

    if require_hash:
        sealed_action = action if action is not None else approval.action
        sealed_args = args if args is not None else stored_args(approval)
        results.append(
            predicate_action_hash(approval, action=sealed_action, args=sealed_args)
        )
    else:
        results.append(PredicateResult("action_hash", True, "skipped"))
    return results


def assert_predicates(results: list[PredicateResult]) -> None:
    """Raise ChallengeRejected on the first failing predicate."""
    for result in results:
        if not result.ok:
            raise ChallengeRejected(result.detail or result.name)


def _lookup(session: Session, nonce: str) -> Approval | None:
    return session.query(Approval).filter(Approval.nonce == nonce).first()


def invoke(
    session: Session,
    *,
    principal: Principal,
    tool_name: str,
    args: dict[str, Any] | None = None,
    tools: dict[str, ToolSpec] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Invoke a registry tool, minting a challenge when tier >= 2."""
    registry = tools if tools is not None else TOOLS
    tool = registry.get(tool_name)
    if tool is None:
        return {"error": "unknown_tool", "tool": tool_name}
    if principal.population not in tool.allowed_populations:
        return {"error": "tool_not_allowed", "tool": tool_name}

    tool_args = dict(args or {})
    if tool.tier < 2:
        result = tool.handler(**tool_args, principal=principal, session=session)
        if isinstance(result, dict):
            return result
        return {"result": result}

    approval = mint_challenge(
        session,
        principal=principal,
        action=tool_name,
        args=tool_args,
        now=now,
    )
    return {
        "status": "confirmation_required",
        "nonce": approval.nonce,
        "action": tool_name,
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else "",
        "message": f"Confirm with CONFIRM {approval.nonce} or DENY {approval.nonce}",
    }


def confirm(
    session: Session,
    *,
    principal: Principal,
    nonce: str,
    tools: dict[str, ToolSpec] | None = None,
    now: datetime | None = None,
    args_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Confirm a pending challenge and execute the sealed tool call."""
    approval = _lookup(session, nonce)
    sealed_args = stored_args(approval) if approval is not None else {}
    check_args = sealed_args if args_override is None else dict(args_override)
    check_action = approval.action if approval is not None else ""
    results = evaluate_predicates(
        approval,
        nonce=nonce,
        principal=principal,
        action=check_action,
        args=check_args,
        now=now,
        require_hash=True,
    )
    assert_predicates(results)
    assert approval is not None

    registry = tools if tools is not None else TOOLS
    tool = registry.get(approval.action)
    if tool is None:
        raise ChallengeRejected(f"unknown action {approval.action}")

    approval.state = ApprovalState.CONFIRMED.value
    approval.resolved_at = now or datetime.now(UTC)
    session.commit()

    result = tool.handler(**sealed_args, principal=principal, session=session)
    payload = {
        "status": "confirmed",
        "nonce": nonce,
        "action": approval.action,
        "result": result,
    }
    return payload


def deny(
    session: Session,
    *,
    principal: Principal,
    nonce: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Deny a pending challenge without executing the tool."""
    approval = _lookup(session, nonce)
    results = evaluate_predicates(
        approval,
        nonce=nonce,
        principal=principal,
        now=now,
        require_hash=False,
    )
    assert_predicates(results)
    assert approval is not None

    approval.state = ApprovalState.DENIED.value
    approval.resolved_at = now or datetime.now(UTC)
    session.commit()
    return {"status": "denied", "nonce": nonce, "action": approval.action}
