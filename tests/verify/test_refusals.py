"""Unit tests for verification refusal paths."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import (
    Approval,
    ApprovalState,
    Base,
    ChannelBinding,
    Org,
    Population,
    Principal,
)
from cerebro.registry import ToolSpec
from cerebro.verify.executor import (
    ENROLL_GUIDANCE,
    REFUSAL_SAME_CHANNEL,
    REFUSAL_SINGLE_CHANNEL,
    REFUSAL_WRONG_PRINCIPAL,
    ChallengeRejected,
    confirm,
    invoke,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC)))
    session.commit()
    yield session
    session.close()


def _principal(session, pid: str, email: str) -> Principal:
    principal = Principal(
        id=pid,
        org_id="org_1",
        population=Population.DEV,
        email=email,
        created_at=datetime.now(UTC),
    )
    session.add(principal)
    session.commit()
    return principal


def _bind(session, principal_id: str, binding_id: str, channel: str, channel_id: str) -> None:
    session.add(
        ChannelBinding(
            id=binding_id,
            principal_id=principal_id,
            channel=channel,
            channel_id=channel_id,
            verified="verified",
            created_at=datetime.now(UTC),
        )
    )
    session.commit()


def _tier2():
    return {
        "risky.deploy": ToolSpec(
            name="risky.deploy",
            description="tier-2",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kwargs: {"ok": True},
            allowed_populations=frozenset(Population),
            tier=2,
        )
    }


def test_single_bound_channel_refuses_with_enroll_guidance(db_session):
    """One verified channel refuses tier-2 invoke and writes an audit Approval."""
    principal = _principal(db_session, "p1", "a@test.com")
    _bind(db_session, "p1", "b1", "telegram", "tg-1")

    outcome = invoke(
        db_session,
        principal=principal,
        tool_name="risky.deploy",
        args={},
        channel="telegram",
        tools=_tier2(),
    )

    assert outcome["status"] == "refused"
    assert outcome["reason"] == REFUSAL_SINGLE_CHANNEL
    assert outcome["message"] == ENROLL_GUIDANCE
    audit = db_session.query(Approval).filter(Approval.id == outcome["approval_id"]).one()
    assert audit.state == ApprovalState.DENIED.value
    assert REFUSAL_SINGLE_CHANNEL in audit.action
    assert REFUSAL_SINGLE_CHANNEL in audit.payload_json


def test_same_channel_confirm_refuses_with_audit(db_session):
    """Confirming on the mint channel is refused and audited."""
    principal = _principal(db_session, "p1", "a@test.com")
    _bind(db_session, "p1", "b1", "telegram", "tg-1")
    _bind(db_session, "p1", "b2", "slack", "U1")

    minted = invoke(
        db_session,
        principal=principal,
        tool_name="risky.deploy",
        args={},
        channel="telegram",
        tools=_tier2(),
    )
    assert minted["status"] == "confirmation_required"

    with pytest.raises(ChallengeRejected, match="same-channel"):
        confirm(
            db_session,
            principal=principal,
            nonce=minted["nonce"],
            channel="telegram",
            tools=_tier2(),
        )

    audits = (
        db_session.query(Approval)
        .filter(Approval.action == f"refusal.{REFUSAL_SAME_CHANNEL}")
        .all()
    )
    assert len(audits) == 1
    assert audits[0].state == ApprovalState.DENIED.value
    pending = db_session.query(Approval).filter(Approval.nonce == minted["nonce"]).one()
    assert pending.state == ApprovalState.PENDING.value


def test_wrong_principal_confirm_refuses_with_audit(db_session):
    """A different principal confirming is refused and audited."""
    owner = _principal(db_session, "owner", "owner@test.com")
    other = _principal(db_session, "other", "other@test.com")
    _bind(db_session, "owner", "b1", "telegram", "tg-owner")
    _bind(db_session, "owner", "b2", "slack", "U-owner")
    _bind(db_session, "other", "b3", "telegram", "tg-other")
    _bind(db_session, "other", "b4", "discord", "d-other")

    minted = invoke(
        db_session,
        principal=owner,
        tool_name="risky.deploy",
        args={},
        channel="telegram",
        tools=_tier2(),
    )

    with pytest.raises(ChallengeRejected, match="wrong principal"):
        confirm(
            db_session,
            principal=other,
            nonce=minted["nonce"],
            channel="slack",
            tools=_tier2(),
        )

    audits = (
        db_session.query(Approval)
        .filter(Approval.action == f"refusal.{REFUSAL_WRONG_PRINCIPAL}")
        .all()
    )
    assert len(audits) == 1
    assert audits[0].principal_id == "other"
    assert audits[0].state == ApprovalState.DENIED.value
    pending = db_session.query(Approval).filter(Approval.nonce == minted["nonce"]).one()
    assert pending.state == ApprovalState.PENDING.value
