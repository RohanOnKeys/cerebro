"""Unit tests for the tier-gated confirm executor."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import (
    ApprovalState,
    Base,
    ChannelBinding,
    Org,
    Population,
    Principal,
)
from cerebro.registry import ToolSpec
from cerebro.verify.challenge import mint_challenge
from cerebro.verify.executor import (
    confirm,
    deny,
    invoke,
    predicate_action_hash,
    predicate_alphabet,
    predicate_exists,
    predicate_not_expired,
    predicate_pending,
    predicate_principal,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC)))
    session.add(
        Principal(
            id="principal_1",
            org_id="org_1",
            population=Population.DEV,
            email="dev@test.com",
            created_at=datetime.now(UTC),
        )
    )
    session.add(
        ChannelBinding(
            id="bind_tg",
            principal_id="principal_1",
            channel="telegram",
            channel_id="tg-1",
            verified="verified",
            created_at=datetime.now(UTC),
        )
    )
    session.add(
        ChannelBinding(
            id="bind_slack",
            principal_id="principal_1",
            channel="slack",
            channel_id="U1",
            verified="verified",
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


def _tier2_tools(handler):
    return {
        "risky.deploy": ToolSpec(
            name="risky.deploy",
            description="tier-2 demo",
            parameters={"type": "object", "properties": {"target": {"type": "string"}}},
            handler=handler,
            allowed_populations=frozenset(Population),
            tier=2,
        ),
        "safe.ping": ToolSpec(
            name="safe.ping",
            description="tier-1 demo",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kwargs: {"pong": True},
            allowed_populations=frozenset(Population),
            tier=1,
        ),
    }


def test_six_predicates_unit():
    """Each of the six predicates can pass and fail independently."""
    assert predicate_alphabet("ABCDEFGH").ok is True
    assert predicate_alphabet("O0IL").ok is False

    assert predicate_exists(None).ok is False

    class _A:
        state = ApprovalState.PENDING.value
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        principal_id = "principal_1"
        payload_json = "{}"

    pending = _A()
    assert predicate_pending(pending).ok is True
    pending.state = ApprovalState.CONFIRMED.value
    assert predicate_pending(pending).ok is False

    pending.state = ApprovalState.PENDING.value
    pending.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert predicate_not_expired(pending).ok is False

    class _P:
        id = "principal_1"

    assert predicate_principal(pending, _P()).ok is True

    from cerebro.verify.challenge import compute_action_hash
    import json

    args = {"target": "prod"}
    digest = compute_action_hash("risky.deploy", args)
    pending.payload_json = json.dumps({"args": args, "action_hash": digest})
    assert predicate_action_hash(pending, action="risky.deploy", args=args).ok is True
    assert predicate_action_hash(
        pending, action="risky.deploy", args={"target": "staging"}
    ).ok is False


def test_tier2_first_call_mints_challenge_without_executing(db_session, principal):
    """tier>=2 invoke returns a nonce and does not call the handler."""
    calls: list[dict] = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"deployed": True}

    tools = _tier2_tools(handler)
    outcome = invoke(
        db_session,
        principal=principal,
        tool_name="risky.deploy",
        args={"target": "prod"},
        channel="telegram",
        tools=tools,
    )
    assert outcome["status"] == "confirmation_required"
    assert outcome["nonce"]
    assert calls == []

    safe = invoke(
        db_session,
        principal=principal,
        tool_name="safe.ping",
        tools=tools,
    )
    assert safe == {"pong": True}


def test_confirm_executes_after_challenge(db_session, principal):
    """CONFIRM executes the sealed handler exactly once."""
    calls: list[dict] = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"deployed": kwargs.get("target")}

    tools = _tier2_tools(handler)
    outcome = invoke(
        db_session,
        principal=principal,
        tool_name="risky.deploy",
        args={"target": "prod"},
        channel="telegram",
        tools=tools,
    )
    confirmed = confirm(
        db_session,
        principal=principal,
        nonce=outcome["nonce"],
        channel="slack",
        tools=tools,
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["result"] == {"deployed": "prod"}
    assert len(calls) == 1


def test_deny_does_not_execute(db_session, principal):
    """DENY resolves the challenge without running the handler."""
    calls: list[dict] = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"deployed": True}

    tools = _tier2_tools(handler)
    outcome = invoke(
        db_session,
        principal=principal,
        tool_name="risky.deploy",
        args={"target": "prod"},
        channel="telegram",
        tools=tools,
    )
    denied = deny(db_session, principal=principal, nonce=outcome["nonce"])
    assert denied["status"] == "denied"
    assert calls == []


def test_command_path_confirm_deny(db_session, principal):
    """CONFIRM/DENY command wiring uses the executor."""
    from cerebro.ingress.commands import parse_command
    from cerebro.main import execute_command
    import cerebro.registry as registry_mod

    calls: list[dict] = []

    def handler(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    tool = ToolSpec(
        name="risky.deploy",
        description="tier-2",
        parameters={"type": "object", "properties": {}},
        handler=handler,
        allowed_populations=frozenset(Population),
        tier=2,
    )
    registry_mod.TOOLS["risky.deploy"] = tool
    try:
        minted = invoke(
            db_session,
            principal=principal,
            tool_name="risky.deploy",
            args={},
            channel="telegram",
            tools=registry_mod.TOOLS,
        )
        reply = execute_command(
            parse_command(f"CONFIRM {minted['nonce']}"),
            principal,
            db_session,
            channel="slack",
        )
        assert reply == f"Confirmed action for {minted['nonce']}"
        assert len(calls) == 1

        minted2 = invoke(
            db_session,
            principal=principal,
            tool_name="risky.deploy",
            args={},
            channel="telegram",
            tools=registry_mod.TOOLS,
        )
        deny_reply = execute_command(
            parse_command(f"DENY {minted2['nonce']}"),
            principal,
            db_session,
            channel="slack",
        )
        assert deny_reply == f"Denied action for {minted2['nonce']}"
        assert len(calls) == 1
    finally:
        registry_mod.TOOLS.pop("risky.deploy", None)
