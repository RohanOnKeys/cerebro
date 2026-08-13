"""Role-claim approval: a different, already-privileged principal must sign off."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Nudge, Org, Population, Principal, RoleClaim
from cerebro.ingress.commands import CommandVerb, parse_command
from cerebro.ingress.enrollment import (
    apply_enrollment_population,
    complete_enrollment,
    start_enrollment,
)
from cerebro.verify.role_claims import (
    RoleClaimRejected,
    approve_role_claim,
    deny_role_claim,
    mint_role_claim,
    notify_eligible_approvers,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Org(id="org_1", name="Test Org", created_at=datetime.now(UTC)))
    session.commit()
    yield session
    session.close()


def _principal(db_session, *, id: str, population: Population) -> Principal:
    principal = Principal(
        id=id, org_id="org_1", population=population, created_at=datetime.now(UTC)
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def test_mint_role_claim_persists_pending_row(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)

    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.DEV
    )

    row = db_session.query(RoleClaim).filter(RoleClaim.id == claim.id).one()
    assert row.status == "pending"
    assert row.requested_population == "dev"
    assert row.claimant_principal_id == "p_ops"


def test_notify_eligible_approvers_only_nudges_ranked_high_enough(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    _principal(db_session, id="p_ops_2", population=Population.OPS)
    dev = _principal(db_session, id="p_dev", population=Population.DEV)
    lead = _principal(db_session, id="p_lead", population=Population.LEAD)

    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.DEV
    )
    notify_eligible_approvers(db_session, claim)

    notified = {n.principal_id for n in db_session.query(Nudge).all()}
    assert notified == {dev.id, lead.id}


def test_approve_by_eligible_dev_flips_population(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    dev = _principal(db_session, id="p_dev", population=Population.DEV)
    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.DEV
    )

    result = approve_role_claim(db_session, approver=dev, nonce=claim.nonce)

    assert result["status"] == "approved"
    assert result["population"] == "dev"
    refreshed = db_session.query(Principal).filter(Principal.id == "p_ops").one()
    assert refreshed.population == Population.DEV


def test_approve_by_under_ranked_ops_is_rejected(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    other_ops = _principal(db_session, id="p_ops_2", population=Population.OPS)
    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.DEV
    )

    with pytest.raises(RoleClaimRejected):
        approve_role_claim(db_session, approver=other_ops, nonce=claim.nonce)


def test_dev_cannot_approve_a_lead_claim(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    dev = _principal(db_session, id="p_dev", population=Population.DEV)
    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.LEAD
    )

    with pytest.raises(RoleClaimRejected):
        approve_role_claim(db_session, approver=dev, nonce=claim.nonce)


def test_lead_can_approve_a_lead_claim(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    lead = _principal(db_session, id="p_lead", population=Population.LEAD)
    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.LEAD
    )

    result = approve_role_claim(db_session, approver=lead, nonce=claim.nonce)

    assert result["population"] == "lead"


def test_approve_by_claimant_themself_is_rejected(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    claimant.population = Population.DEV
    db_session.commit()
    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.LEAD
    )

    with pytest.raises(RoleClaimRejected):
        approve_role_claim(db_session, approver=claimant, nonce=claim.nonce)


def test_approve_unknown_nonce_is_rejected(db_session):
    dev = _principal(db_session, id="p_dev", population=Population.DEV)

    with pytest.raises(RoleClaimRejected):
        approve_role_claim(db_session, approver=dev, nonce="NOPE0000")


def test_approve_expired_claim_is_rejected(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    dev = _principal(db_session, id="p_dev", population=Population.DEV)
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    claim = mint_role_claim(
        db_session,
        claimant=claimant,
        requested_population=Population.DEV,
        now=now,
    )

    with pytest.raises(RoleClaimRejected):
        approve_role_claim(
            db_session, approver=dev, nonce=claim.nonce, now=now + timedelta(hours=25)
        )


def test_deny_leaves_claimant_unchanged(db_session):
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)
    dev = _principal(db_session, id="p_dev", population=Population.DEV)
    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.DEV
    )

    result = deny_role_claim(db_session, approver=dev, nonce=claim.nonce)

    assert result["status"] == "denied"
    refreshed = db_session.query(Principal).filter(Principal.id == "p_ops").one()
    assert refreshed.population == Population.OPS


def test_zero_eligible_approvers_leaves_claim_pending_forever(db_session):
    """Known, accepted gap: a fresh org with no eligible approver never resolves."""
    claimant = _principal(db_session, id="p_ops", population=Population.OPS)

    claim = mint_role_claim(
        db_session, claimant=claimant, requested_population=Population.ADMIN
    )
    nudges = notify_eligible_approvers(db_session, claim)

    assert nudges == []
    row = db_session.query(RoleClaim).filter(RoleClaim.id == claim.id).one()
    assert row.status == "pending"


def test_apply_enrollment_population_noop_for_client_and_ops(db_session):
    client = _principal(db_session, id="p_client", population=Population.CLIENT)
    ops = _principal(db_session, id="p_ops", population=Population.OPS)

    assert apply_enrollment_population(db_session, client, Population.CLIENT) is None
    assert apply_enrollment_population(db_session, ops, Population.OPS) is None
    assert db_session.query(RoleClaim).count() == 0


def test_existing_dev_reclaiming_lead_keeps_dev_while_pending(db_session):
    dev = _principal(db_session, id="p_dev", population=Population.DEV)

    claim = apply_enrollment_population(db_session, dev, Population.LEAD)

    assert claim is not None
    refreshed = db_session.query(Principal).filter(Principal.id == "p_dev").one()
    assert refreshed.population == Population.DEV


def test_complete_enrollment_seeds_ops_and_opens_a_claim_for_gated_population(
    db_session,
):
    _principal(db_session, id="p_dev", population=Population.DEV)
    pending = start_enrollment(
        db_session, org_id="org_1", channel="telegram", channel_id="tg_1", conversation_id="c1"
    )

    principal, _binding, claim = complete_enrollment(
        db_session, pending=pending, population=Population.DEV, email="new@example.com"
    )

    assert principal.population == Population.OPS
    assert claim is not None
    assert claim.status == "pending"


def test_complete_enrollment_ungated_population_behaves_as_before(db_session):
    pending = start_enrollment(
        db_session, org_id="org_1", channel="telegram", channel_id="tg_1", conversation_id="c1"
    )

    principal, _binding, claim = complete_enrollment(
        db_session, pending=pending, population=Population.CLIENT, email="c@example.com"
    )

    assert principal.population == Population.CLIENT
    assert claim is None


def test_approve_reject_are_parseable_commands():
    assert parse_command("APPROVE ABCD1234").verb == CommandVerb.APPROVE
    assert parse_command("REJECT ABCD1234").verb == CommandVerb.REJECT
