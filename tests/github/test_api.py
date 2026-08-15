"""Unit tests for GitHub API T0 reads and CI tool handlers."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, CiRun, Org, Population, Principal
from cerebro.github.api import GitHubAPI
from cerebro.github.app_auth import GitHubAppAuth
from cerebro.github.runs import explain_ci_failure, list_ci_runs_live, upsert_from_github
from cerebro.registry import TOOLS, TOOLS_FOR


@pytest.fixture
def rsa_pem_b64() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode("ascii")


@pytest.fixture
def auth(rsa_pem_b64) -> GitHubAppAuth:
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "token": "ghs_test",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    http.post.return_value = response
    return GitHubAppAuth(
        app_id="12345",
        private_key_b64=rsa_pem_b64,
        installation_id="67890",
        http_client=http,
    )


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Org(id="org_1", name="Test Org", join_code="TESTORG", created_at=datetime.now(UTC)))
    session.add(
        Principal(
            id="principal_dev",
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
    return db_session.query(Principal).filter(Principal.id == "principal_dev").one()


def test_list_workflow_runs_is_get_only(auth):
    """list_workflow_runs issues a GET to the Actions runs endpoint."""
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "workflow_runs": [
            {
                "id": 42,
                "name": "CI",
                "head_branch": "main",
                "head_sha": "abc",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://example/runs/42",
                "event": "push",
            }
        ]
    }
    http.get.return_value = response
    api = GitHubAPI(auth, http_client=http)
    runs = api.list_workflow_runs("acme", "cerebro", branch="main")
    assert len(runs) == 1
    assert runs[0]["id"] == 42
    path = http.get.call_args.args[0]
    assert path.endswith("/repos/acme/cerebro/actions/runs")
    assert http.get.call_args.kwargs["params"]["branch"] == "main"


def test_upsert_and_list_ci_runs_live(db_session, auth):
    """list_ci_runs_live upserts GitHub payloads into the ci_runs ledger."""
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "workflow_runs": [
            {
                "id": 99,
                "name": "CI",
                "head_branch": "feat/x",
                "head_sha": "deadbeef",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://example/runs/99",
                "event": "pull_request",
            }
        ]
    }
    http.get.return_value = response
    api = GitHubAPI(auth, http_client=http)

    rows = list_ci_runs_live(
        db_session, api, org_id="org_1", owner="acme", repo="cerebro"
    )
    assert len(rows) == 1
    assert rows[0].github_run_id == "99"
    assert rows[0].conclusion == "failure"

    again = list_ci_runs_live(
        db_session, api, org_id="org_1", owner="acme", repo="cerebro"
    )
    assert len(again) == 1
    assert db_session.query(CiRun).count() == 1


def test_explain_ci_failure_summarizes_failed_steps(db_session, auth):
    """explain_ci_failure collects failed jobs/steps and stores a summary."""
    http = MagicMock()

    def _get(url, **kwargs):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        if url.endswith("/actions/runs/77"):
            response.json.return_value = {
                "id": 77,
                "name": "CI",
                "head_branch": "main",
                "head_sha": "abc",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://example/runs/77",
                "event": "push",
            }
        elif url.endswith("/actions/runs/77/jobs"):
            response.json.return_value = {
                "jobs": [
                    {
                        "id": 5001,
                        "name": "test",
                        "conclusion": "failure",
                        "status": "completed",
                        "html_url": "https://example/jobs/5001",
                        "steps": [
                            {"name": "Checkout", "number": 1, "conclusion": "success"},
                            {"name": "pytest", "number": 2, "conclusion": "failure"},
                        ],
                    }
                ]
            }
        elif url.endswith("/check-runs/5001/annotations"):
            response.json.return_value = [
                {
                    "path": "tests/test_x.py",
                    "start_line": 10,
                    "message": "assert False",
                    "annotation_level": "failure",
                }
            ]
        else:
            raise AssertionError(f"unexpected url {url}")
        return response

    http.get.side_effect = _get
    api = GitHubAPI(auth, http_client=http)
    result = explain_ci_failure(
        db_session, api, org_id="org_1", owner="acme", repo="cerebro", run_id=77
    )
    assert "pytest" in result["summary"]
    assert result["failed_jobs"][0]["failed_steps"][0]["name"] == "pytest"
    assert result["failed_jobs"][0]["annotations"][0]["message"] == "assert False"
    row = db_session.query(CiRun).filter(CiRun.github_run_id == "77").one()
    assert "pytest" in (row.failure_summary or "")


def test_ci_runs_unique_org_github_run_id(db_session):
    """(org_id, github_run_id) uniqueness is enforced."""
    upsert_from_github(
        db_session,
        org_id="org_1",
        owner="acme",
        repo="cerebro",
        payload={
            "id": 1,
            "name": "CI",
            "head_branch": "main",
            "head_sha": "a",
            "status": "completed",
            "conclusion": "success",
            "html_url": "u",
            "event": "push",
        },
    )
    db_session.commit()
    upsert_from_github(
        db_session,
        org_id="org_1",
        owner="acme",
        repo="cerebro",
        payload={
            "id": 1,
            "name": "CI",
            "head_branch": "main",
            "head_sha": "b",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "u",
            "event": "push",
        },
    )
    db_session.commit()
    assert db_session.query(CiRun).count() == 1
    assert db_session.query(CiRun).one().head_sha == "b"


def test_ci_runs_table_indexes_exist():
    """create_all materializes the ci_runs unique org/run index."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    indexes = {index["name"]: index for index in inspect(engine).get_indexes("ci_runs")}
    assert indexes["ix_ci_runs_org_id_github_run_id"]["unique"]
    assert indexes["ix_ci_runs_org_id_github_run_id"]["column_names"] == [
        "org_id",
        "github_run_id",
    ]


def test_list_ci_runs_tool_team_only(db_session, principal):
    """list_ci_runs is team-gated and uses an injected API client."""
    assert Population.CLIENT not in TOOLS["list_ci_runs"].allowed_populations
    assert "list_ci_runs" in {t.name for t in TOOLS_FOR[Population.DEV]}
    assert "list_ci_runs" not in {t.name for t in TOOLS_FOR[Population.CLIENT]}

    api = MagicMock()
    api.list_workflow_runs.return_value = [
        {
            "id": 5,
            "name": "CI",
            "head_branch": "main",
            "head_sha": "abc",
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://example/5",
            "event": "push",
        }
    ]
    result = TOOLS["list_ci_runs"].handler(
        session=db_session,
        principal=principal,
        owner="acme",
        repo="cerebro",
        api=api,
    )
    assert result["count"] == 1
    assert result["runs"][0]["github_run_id"] == "5"


def test_explain_ci_failure_tool(db_session, principal):
    """explain_ci_failure tool wraps the runs helper via an injected API."""
    api = MagicMock()
    api.get_workflow_run.return_value = {
        "id": 8,
        "name": "CI",
        "head_branch": "main",
        "head_sha": "abc",
        "status": "completed",
        "conclusion": "failure",
        "html_url": "https://example/8",
        "event": "push",
    }
    api.list_jobs_for_run.return_value = [
        {
            "id": 1,
            "name": "build",
            "conclusion": "failure",
            "status": "completed",
            "html_url": "https://example/job/1",
            "steps": [{"name": "compile", "number": 1, "conclusion": "failure"}],
        }
    ]
    api.list_annotations_for_check_run.return_value = []
    result = TOOLS["explain_ci_failure"].handler(
        session=db_session,
        principal=principal,
        owner="acme",
        repo="cerebro",
        run_id="8",
        api=api,
    )
    assert "compile" in result["summary"]
    assert result["run"]["github_run_id"] == "8"
