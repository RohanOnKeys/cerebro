"""Unit tests for membrane crossing policy lookup: one test per seeded rule."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Policy
from cerebro.membrane.policy import (
    DEFAULT_POLICIES,
    evaluate_crossing,
    seed_default_policies,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_default_policies(session)
    yield session
    session.close()


def test_policies_table_is_never_empty_after_seeding(db_session):
    """Gate: policies is never empty."""
    assert db_session.query(Policy).count() == len(DEFAULT_POLICIES) == 6


def test_dev_to_client_redacts_stack_trace_and_estimate(db_session):
    decision = evaluate_crossing(db_session, source="dev", target="client")
    assert decision.action == "redact"
    assert set(decision.redact_fields) == {"stack_trace", "estimate"}


def test_ops_to_client_redacts_estimate_only(db_session):
    decision = evaluate_crossing(db_session, source="ops", target="client")
    assert decision.action == "redact"
    assert set(decision.redact_fields) == {"estimate"}


def test_lead_to_client_redacts_estimate_and_risk(db_session):
    decision = evaluate_crossing(db_session, source="lead", target="client")
    assert decision.action == "redact"
    assert set(decision.redact_fields) == {"estimate", "risk"}


def test_admin_to_client_is_denied(db_session):
    """The one explicit DENY rule."""
    decision = evaluate_crossing(db_session, source="admin", target="client")
    assert decision.action == "deny"
    assert decision.redact_fields == ()


def test_client_to_dev_is_allowed_unredacted(db_session):
    decision = evaluate_crossing(db_session, source="client", target="dev")
    assert decision.action == "allow"
    assert decision.redact_fields == ()


def test_client_to_ops_is_allowed_unredacted(db_session):
    decision = evaluate_crossing(db_session, source="client", target="ops")
    assert decision.action == "allow"
    assert decision.redact_fields == ()


# --- one denial per rule: any pair not in the seed data fails closed ---


@pytest.mark.parametrize(
    "source,target",
    [
        ("admin", "ops"),  # not seeded
        ("dev", "ops"),  # not seeded
        ("ops", "dev"),  # not seeded
        ("client", "lead"),  # not seeded
        ("client", "admin"),  # not seeded
        ("lead", "dev"),  # not seeded
    ],
)
def test_unlisted_crossings_fail_closed_to_deny(db_session, source, target):
    decision = evaluate_crossing(db_session, source=source, target=target)
    assert decision.action == "deny"


def test_seeding_is_idempotent(db_session):
    """Re-seeding an already-populated table is a no-op, not a duplicate insert."""
    seed_default_policies(db_session)
    assert db_session.query(Policy).count() == 6
