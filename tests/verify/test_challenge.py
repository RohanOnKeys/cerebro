"""Unit tests for challenge minting."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import ApprovalState, Base, Org, Population, Principal
from cerebro.verify.challenge import (
    NONCE_ALPHABET,
    compute_action_hash,
    mint_challenge,
    mint_nonce,
    nonce_alphabet_ok,
    stored_action_hash,
    stored_args,
)
from cerebro.verify.executor import ChallengeRejected, confirm, evaluate_predicates


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Org(id="org_1", name="Test Org", created_at=datetime.now(UTC)))
    session.add(
        Principal(
            id="principal_1",
            org_id="org_1",
            population=Population.DEV,
            email="dev@test.com",
            created_at=datetime.now(UTC),
        )
    )
    session.commit()
    yield session
    session.close()


@pytest.fixture
def principal(db_session):
    """Load the fixture principal."""
    return db_session.query(Principal).one()


def test_nonce_uses_unambiguous_alphabet_only():
    """Minted nonces never include ambiguous 0/O/1/I/L characters."""
    for _ in range(50):
        nonce = mint_nonce(16)
        assert nonce_alphabet_ok(nonce)
        assert all(ch in NONCE_ALPHABET for ch in nonce)
        assert "0" not in nonce and "O" not in nonce
        assert "1" not in nonce and "I" not in nonce and "L" not in nonce


def test_challenge_expires(db_session, principal):
    """An expired challenge fails the not_expired predicate."""
    now = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    approval = mint_challenge(
        db_session,
        principal=principal,
        action="demo.tool",
        args={"x": 1},
        ttl=timedelta(minutes=5),
        now=now,
    )
    results = evaluate_predicates(
        approval,
        nonce=approval.nonce,
        principal=principal,
        now=now + timedelta(minutes=6),
    )
    by_name = {item.name: item for item in results}
    assert by_name["not_expired"].ok is False


def test_challenge_replay_rejected(db_session, principal):
    """Confirming twice fails because state is no longer pending."""
    calls: list[dict] = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    from cerebro.db.models import Population
    from cerebro.registry import ToolSpec

    tools = {
        "demo.tool": ToolSpec(
            name="demo.tool",
            description="demo",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            allowed_populations=frozenset(Population),
            tier=2,
        )
    }
    approval = mint_challenge(
        db_session,
        principal=principal,
        action="demo.tool",
        args={"n": 1},
    )
    confirm(
        db_session,
        principal=principal,
        nonce=approval.nonce,
        tools=tools,
    )
    with pytest.raises(ChallengeRejected, match="state is confirmed"):
        confirm(
            db_session,
            principal=principal,
            nonce=approval.nonce,
            tools=tools,
        )
    assert len(calls) == 1


def test_mutated_args_fail_action_hash(db_session, principal):
    """Tampered args change the hash and fail verification."""
    approval = mint_challenge(
        db_session,
        principal=principal,
        action="demo.tool",
        args={"branch": "main"},
    )
    sealed = stored_action_hash(approval)
    assert sealed == compute_action_hash("demo.tool", {"branch": "main"})
    mutated = compute_action_hash("demo.tool", {"branch": "evil"})
    assert mutated != sealed

    results = evaluate_predicates(
        approval,
        nonce=approval.nonce,
        principal=principal,
        action="demo.tool",
        args={"branch": "evil"},
    )
    by_name = {item.name: item for item in results}
    assert by_name["action_hash"].ok is False
    assert stored_args(approval) == {"branch": "main"}


def test_mint_challenge_sets_pending_and_hash(db_session, principal):
    """mint_challenge writes a pending approval with sealed action_hash."""
    approval = mint_challenge(
        db_session,
        principal=principal,
        action="demo.tool",
        args={"a": True},
    )
    assert approval.state == ApprovalState.PENDING.value
    assert nonce_alphabet_ok(approval.nonce)
    assert stored_action_hash(approval) == compute_action_hash("demo.tool", {"a": True})
