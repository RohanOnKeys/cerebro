"""Role-claim approval: DEV/LEAD/ADMIN claims need an existing peer's sign-off.

Deliberately not a reuse of verify/challenge.py + verify/executor.py: that
system's predicate is "the same principal confirms from a second channel" and
explicitly refuses a different principal confirming. Role-claim approval needs
the opposite predicate: a different, already-privileged principal approves
someone else's claim. Same nonce/TTL shape as challenge.py, separate table and
separate predicates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from cerebro.db.models import NudgeKind, Nudge, Population, Principal, RoleClaim, RoleClaimStatus
from cerebro.services import nudges as nudges_service
from cerebro.verify.challenge import mint_nonce

DEFAULT_TTL = timedelta(hours=24)

# Strict ladder: a claim for population P needs an approver ranked >= P.
PRIVILEGE_RANK: dict[Population, int] = {
    Population.OPS: 0,
    Population.DEV: 1,
    Population.LEAD: 2,
    Population.ADMIN: 3,
}


class RoleClaimRejected(ValueError):
    """Raised when an APPROVE/REJECT fails a predicate."""


def _rank(population: Population | str) -> int:
    pop = population if isinstance(population, Population) else Population(population)
    return PRIVILEGE_RANK.get(pop, 0)


def mint_role_claim(
    session: Session,
    *,
    claimant: Principal,
    requested_population: Population,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> RoleClaim:
    """Persist a pending role claim."""
    moment = now or datetime.now(UTC)
    claim = RoleClaim(
        id=str(uuid.uuid4()),
        org_id=claimant.org_id,
        claimant_principal_id=claimant.id,
        requested_population=requested_population.value,
        nonce=mint_nonce(),
        status=RoleClaimStatus.PENDING.value,
        expires_at=moment + ttl,
        created_at=moment,
    )
    session.add(claim)
    session.commit()
    return claim


def notify_eligible_approvers(session: Session, claim: RoleClaim) -> list[Nudge]:
    """Nudge every principal ranked high enough to approve this claim."""
    required_rank = _rank(claim.requested_population)
    candidates = (
        session.query(Principal)
        .filter(
            Principal.org_id == claim.org_id,
            Principal.id != claim.claimant_principal_id,
        )
        .all()
    )
    eligible = [p for p in candidates if _rank(p.population) >= required_rank]
    body = (
        f"{claim.claimant_principal_id} is requesting {claim.requested_population}. "
        f"Reply APPROVE {claim.nonce} or REJECT {claim.nonce}."
    )
    return [
        nudges_service.create_nudge(
            session,
            org_id=claim.org_id,
            principal_id=approver.id,
            body=body,
            kind=NudgeKind.ROLE_CLAIM_PENDING.value,
        )
        for approver in eligible
    ]


def _lookup(session: Session, nonce: str) -> RoleClaim | None:
    return session.query(RoleClaim).filter(RoleClaim.nonce == nonce).first()


def _assert_eligible(
    claim: RoleClaim | None, *, approver: Principal, nonce: str, now: datetime
) -> RoleClaim:
    if claim is None:
        raise RoleClaimRejected(f"unknown nonce {nonce}")
    if claim.status != RoleClaimStatus.PENDING.value:
        raise RoleClaimRejected(f"claim is {claim.status}, not pending")
    expires = claim.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires is None or now >= expires:
        raise RoleClaimRejected("claim expired")
    if approver.org_id != claim.org_id:
        raise RoleClaimRejected("approver is in a different org")
    if approver.id == claim.claimant_principal_id:
        raise RoleClaimRejected("cannot approve your own claim")
    if _rank(approver.population) < _rank(claim.requested_population):
        raise RoleClaimRejected(
            f"{approver.population.value} cannot approve a "
            f"{claim.requested_population} claim"
        )
    return claim


def approve_role_claim(
    session: Session, *, approver: Principal, nonce: str, now: datetime | None = None
) -> dict[str, Any]:
    """Approve a pending role claim; promotes the claimant on success."""
    moment = now or datetime.now(UTC)
    claim = _assert_eligible(
        _lookup(session, nonce), approver=approver, nonce=nonce, now=moment
    )

    claimant = (
        session.query(Principal).filter(Principal.id == claim.claimant_principal_id).first()
    )
    if claimant is None:
        raise RoleClaimRejected("claimant no longer exists")

    claimant.population = Population(claim.requested_population)
    claim.status = RoleClaimStatus.APPROVED.value
    claim.approver_principal_id = approver.id
    claim.resolved_at = moment
    session.commit()

    nudges_service.create_nudge(
        session,
        org_id=claim.org_id,
        principal_id=claimant.id,
        body=f"Your {claim.requested_population} claim was approved by {approver.id}.",
        kind=NudgeKind.ROLE_CLAIM_RESOLVED.value,
    )
    return {
        "status": "approved",
        "nonce": nonce,
        "claimant_principal_id": claimant.id,
        "population": claimant.population.value,
    }


def deny_role_claim(
    session: Session, *, approver: Principal, nonce: str, now: datetime | None = None
) -> dict[str, Any]:
    """Deny a pending role claim; the claimant's population is left untouched."""
    moment = now or datetime.now(UTC)
    claim = _assert_eligible(
        _lookup(session, nonce), approver=approver, nonce=nonce, now=moment
    )

    claim.status = RoleClaimStatus.DENIED.value
    claim.approver_principal_id = approver.id
    claim.resolved_at = moment
    session.commit()

    nudges_service.create_nudge(
        session,
        org_id=claim.org_id,
        principal_id=claim.claimant_principal_id,
        body=f"Your {claim.requested_population} claim was denied by {approver.id}.",
        kind=NudgeKind.ROLE_CLAIM_RESOLVED.value,
    )
    return {
        "status": "denied",
        "nonce": nonce,
        "claimant_principal_id": claim.claimant_principal_id,
    }
