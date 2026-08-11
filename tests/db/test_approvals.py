"""Unit tests for the approvals ledger model constraints."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Approval, ApprovalState, Base, Org, Population, Principal


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    org = Org(id="org_1", name="Test Org", created_at=datetime.now(UTC))
    session.add(org)
    principal = Principal(
        id="principal_1",
        org_id="org_1",
        population=Population.DEV,
        email="dev@test.com",
        created_at=datetime.now(UTC),
    )
    session.add(principal)
    session.commit()
    yield session
    session.close()


def _approval(*, nonce: str, approval_id: str = "apr_1") -> Approval:
    now = datetime.now(UTC)
    return Approval(
        id=approval_id,
        org_id="org_1",
        principal_id="principal_1",
        nonce=nonce,
        state=ApprovalState.PENDING.value,
        action="ci.dispatch",
        payload_json="{}",
        expires_at=now + timedelta(minutes=10),
        created_at=now,
    )


def test_approval_nonce_is_unique(db_session):
    """Duplicate nonce values must violate the unique constraint."""
    db_session.add(_approval(nonce="7qk3x2", approval_id="apr_1"))
    db_session.commit()

    db_session.add(_approval(nonce="7qk3x2", approval_id="apr_2"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_approval_indexes_include_state_expires_at():
    """Model declares the (state, expires_at) lookup index."""
    indexes = {index.name: tuple(index.columns.keys()) for index in Approval.__table__.indexes}
    assert indexes["ix_approvals_state_expires_at"] == ("state", "expires_at")
    assert indexes["ix_approvals_nonce"] == ("nonce",)
    nonce_index = next(index for index in Approval.__table__.indexes if index.name == "ix_approvals_nonce")
    assert nonce_index.unique is True


def test_approval_create_all_enforces_nonce_unique_and_state_expires_index():
    """create_all materializes unique nonce and (state, expires_at) index."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    indexes = inspector.get_indexes("approvals")
    by_name = {index["name"]: index for index in indexes}

    assert by_name["ix_approvals_nonce"]["unique"]
    assert by_name["ix_approvals_nonce"]["column_names"] == ["nonce"]
    assert by_name["ix_approvals_state_expires_at"]["column_names"] == [
        "state",
        "expires_at",
    ]
