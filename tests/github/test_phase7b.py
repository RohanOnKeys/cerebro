"""Phase 7B: webhook verify/normalize, triage/flake, T2 mutations, task block."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import (
    Base,
    CiFailure,
    CiRun,
    Org,
    Population,
    Principal,
    Task,
    TaskStatus,
)
from cerebro.github.api import GitHubAPI
from cerebro.github.triage import (
    fingerprint_log,
    handle_failed_run,
    link_task_for_run,
    normalize_for_fingerprint,
    slice_log,
)
from cerebro.github.webhook import (
    CIEvent,
    handle_ci_event,
    normalize_workflow_run,
    parse_task_number_from_branch,
    verify_signature,
    WebhookSignatureError,
)
from cerebro.registry import TOOLS
from cerebro.verify import executor as verify_executor


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Org(id="org_1", name="Org", join_code="TESTORG", created_at=datetime.now(UTC)))
    session.add(
        Principal(
            id="p_dev",
            org_id="org_1",
            population=Population.DEV,
            email="d@t.com",
            created_at=datetime.now(UTC),
        )
    )
    session.add(
        Task(
            id="task_12",
            org_id="org_1",
            number=12,
            title="Ship",
            designation="dev",
            status=TaskStatus.ACKED.value,
            assignee_principal_id="p_dev",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()
    yield session
    session.close()


@pytest.fixture
def principal(db_session):
    return db_session.query(Principal).one()


def _event(**kwargs) -> CIEvent:
    raw = {
        "id": int(kwargs.get("run_id", "9")),
        "name": kwargs.get("workflow_name", "CI"),
        "head_branch": kwargs.get("head_branch", "task-12"),
        "head_sha": "abc",
        "status": kwargs.get("status", "completed"),
        "conclusion": kwargs.get("conclusion", "failure"),
        "html_url": "https://example/9",
        "event": "push",
    }
    return CIEvent(
        action="completed",
        owner=kwargs.get("owner", "acme"),
        repo=kwargs.get("repo", "cerebro"),
        run_id=str(raw["id"]),
        status=raw["status"],
        conclusion=str(raw["conclusion"] or ""),
        head_branch=raw["head_branch"],
        head_sha=raw["head_sha"],
        workflow_name=raw["name"],
        html_url=raw["html_url"],
        event=raw["event"],
        raw_run=raw,
    )


def test_verify_signature_ok_and_bad():
    secret = "s3cret"
    body = b'{"ok":true}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    verify_signature(body, sig, secret)
    with pytest.raises(WebhookSignatureError):
        verify_signature(body, "sha256=deadbeef", secret)


def test_normalize_workflow_run():
    payload = {
        "action": "completed",
        "repository": {"full_name": "acme/cerebro"},
        "workflow_run": {
            "id": 42,
            "name": "CI",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "task-12",
            "head_sha": "dead",
            "html_url": "https://x/42",
            "event": "push",
        },
    }
    event = normalize_workflow_run(payload)
    assert event is not None
    assert event.run_id == "42"
    assert event.owner == "acme"
    assert event.conclusion == "failure"


def test_fingerprint_strips_ts_path_pid():
    a = "2026-08-11T12:00:00Z fail at /home/runner/work/app/main.py pid=1234"
    b = "2026-08-11T13:00:00Z fail at /tmp/other/main.py pid=9999"
    assert normalize_for_fingerprint(a) == normalize_for_fingerprint(b)
    assert fingerprint_log(a) == fingerprint_log(b)
    assert len(slice_log("x" * 5000)) == 4000


def test_flake_budget_rerun_then_issue(db_session, monkeypatch):
    monkeypatch.setattr("cerebro.github.triage.settings.ci_flake_budget", 3)
    monkeypatch.setattr("cerebro.github.triage.settings.ci_flake_window_hours", 24)
    api = MagicMock()
    api.create_issue.return_value = {"html_url": "https://github.com/acme/cerebro/issues/1"}
    ci_run = CiRun(
        id="cirun_1",
        org_id="org_1",
        github_run_id="9",
        owner="acme",
        repo="cerebro",
        workflow_name="CI",
        head_branch="task-12",
        head_sha="abc",
        status="completed",
        conclusion="failure",
        html_url="https://example/9",
        event="push",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(ci_run)
    db_session.commit()
    event = _event()
    log = "AssertionError: boom"
    now = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    for i in range(3):
        out = handle_failed_run(
            db_session,
            event=event,
            ci_run=ci_run,
            log_text=log,
            api=api,
            now=now + timedelta(minutes=i),
        )
        assert out["action"] == "rerun"
    assert api.rerun_workflow.call_count == 3
    out = handle_failed_run(
        db_session,
        event=event,
        ci_run=ci_run,
        log_text=log,
        api=api,
        now=now + timedelta(minutes=10),
    )
    assert out["action"] == "open_issue"
    assert out["issue_url"].endswith("/issues/1")
    assert db_session.query(CiFailure).count() == 1


def test_link_task_and_block_on_red(db_session, principal):
    from cerebro.github.triage import block_task_on_red_build

    ci_run = CiRun(
        id="cirun_2",
        org_id="org_1",
        github_run_id="10",
        owner="acme",
        repo="cerebro",
        workflow_name="CI",
        head_branch="task-12",
        head_sha="abc",
        status="completed",
        conclusion="failure",
        html_url="https://example/10",
        event="push",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(ci_run)
    db_session.commit()
    assert parse_task_number_from_branch("task-12") == 12
    assert link_task_for_run(db_session, ci_run, head_branch="task-12") == "task_12"
    blocked = block_task_on_red_build(db_session, ci_run=ci_run, event=_event(run_id="10"))
    assert blocked is not None
    task = db_session.query(Task).filter(Task.id == "task_12").one()
    assert task.status == TaskStatus.BLOCKED.value
    assert "CI red" in (task.blocked_reason or "")


def test_handle_ci_event_resolves_the_real_org_not_a_hardcoded_default(db_session, monkeypatch):
    """The bug this fixes: handle_ci_event used to hardcode
    settings.github_default_org_id ("default_org"), which threw a
    ForeignKeyViolation the moment a real deployment had actual orgs (created
    via the join-code enrollment flow) and none of them was literally named
    "default_org". It must resolve the real active org instead."""
    monkeypatch.setattr("cerebro.config.settings.github_default_org_id", "default_org")
    assert db_session.query(Org).filter(Org.id == "default_org").first() is None

    result = handle_ci_event(db_session, _event(run_id="99", conclusion="success"))

    ci_run = db_session.query(CiRun).filter(CiRun.github_run_id == "99").one()
    assert ci_run.org_id == "org_1"
    assert result["ci_run_id"] == ci_run.id


def test_t2_tools_gated_and_handlers(db_session, principal):
    for name in ("rerun_workflow", "dispatch_workflow", "cancel_run"):
        assert TOOLS[name].tier == 2
    api = MagicMock()
    assert TOOLS["rerun_workflow"].handler(
        session=db_session,
        principal=principal,
        owner="acme",
        repo="cerebro",
        run_id="1",
        api=api,
    )["status"] == "rerun_requested"
    api.rerun_workflow.assert_called_once()
    assert TOOLS["dispatch_workflow"].handler(
        session=db_session,
        principal=principal,
        owner="acme",
        repo="cerebro",
        workflow_id="ci.yml",
        ref="main",
        api=api,
    )["status"] == "dispatched"
    assert TOOLS["cancel_run"].handler(
        session=db_session,
        principal=principal,
        owner="acme",
        repo="cerebro",
        run_id="1",
        api=api,
    )["status"] == "cancel_requested"

    # Verify gate: tier-2 mint without two channels refuses.
    out = verify_executor.invoke(
        db_session,
        principal=principal,
        tool_name="rerun_workflow",
        args={"owner": "acme", "repo": "cerebro", "run_id": "1"},
        channel="slack",
    )
    assert out["status"] == "refused"
