"""Unit tests for the Jira API wrapper and its registry tools."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Org, Population, Principal
from cerebro.jira.api import JiraAPI, JiraAPIError, _text_to_adf
from cerebro.jira.auth import JiraAuth
from cerebro.registry import TOOLS, TOOLS_FOR


@pytest.fixture
def auth() -> JiraAuth:
    return JiraAuth(
        base_url="https://acme.atlassian.net", email="bot@acme.com", api_token="s3cret"
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
            id="p_dev", org_id="org_1", population=Population.DEV, created_at=datetime.now(UTC)
        )
    )
    session.commit()
    yield session
    session.close()


@pytest.fixture
def principal(db_session):
    return db_session.query(Principal).one()


def test_text_to_adf_wraps_single_paragraph():
    adf = _text_to_adf("hello world")
    assert adf["type"] == "doc"
    assert adf["content"][0]["content"][0]["text"] == "hello world"


def test_text_to_adf_empty_text_has_no_content_node():
    adf = _text_to_adf("")
    assert adf["content"][0]["content"] == []


def test_create_issue_sends_basic_auth_and_adf_description(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 201
    response.content = b'{"id": "10001", "key": "PROJ-1"}'
    response.json.return_value = {"id": "10001", "key": "PROJ-1"}
    http.request.return_value = response

    api = JiraAPI(auth, http_client=http)
    result = api.create_issue("PROJ", summary="Fix bug", description="broken export")

    assert result["key"] == "PROJ-1"
    call = http.request.call_args
    assert call.args[0] == "POST"
    assert call.args[1].endswith("/issue")
    assert call.kwargs["headers"]["Authorization"] == auth.basic_auth_header()
    body = call.kwargs["json"]
    assert body["fields"]["project"]["key"] == "PROJ"
    assert body["fields"]["description"]["type"] == "doc"


def test_create_issue_http_error_raises_jira_api_error(auth):
    http = MagicMock()
    request = httpx.Request("POST", "https://x/issue")
    error_response = httpx.Response(400, request=request)
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad", request=request, response=error_response
    )
    http.request.return_value = response

    api = JiraAPI(auth, http_client=http)
    with pytest.raises(JiraAPIError):
        api.create_issue("PROJ", summary="x")


def test_get_issue_returns_payload(auth):
    http = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 200
    response.content = b'{"key": "PROJ-1"}'
    response.json.return_value = {"key": "PROJ-1", "fields": {"summary": "Fix bug"}}
    http.request.return_value = response

    api = JiraAPI(auth, http_client=http)
    result = api.get_issue("PROJ-1")

    assert result["fields"]["summary"] == "Fix bug"


def test_create_jira_ticket_tool_team_only():
    assert Population.CLIENT not in TOOLS["create_jira_ticket"].allowed_populations
    assert "create_jira_ticket" in {t.name for t in TOOLS_FOR[Population.DEV]}
    assert "create_jira_ticket" not in {t.name for t in TOOLS_FOR[Population.CLIENT]}


def test_create_jira_ticket_tool_returns_issue_url(db_session, principal):
    api = MagicMock()
    api.auth.base_url = "https://acme.atlassian.net"
    api.create_issue.return_value = {"id": "10001", "key": "PROJ-1"}

    result = TOOLS["create_jira_ticket"].handler(
        session=db_session,
        principal=principal,
        summary="Fix bug",
        project_key="PROJ",
        api=api,
    )

    assert result["issue_key"] == "PROJ-1"
    assert result["issue_url"] == "https://acme.atlassian.net/browse/PROJ-1"
    assert result["created_by"] == "p_dev"


def test_create_jira_ticket_tool_missing_project_key_errors(db_session, principal, monkeypatch):
    monkeypatch.setattr("cerebro.config.settings.jira_default_project_key", "")

    result = TOOLS["create_jira_ticket"].handler(
        session=db_session, principal=principal, summary="Fix bug", api=MagicMock()
    )

    assert result["error"] == "missing_project_key"


def test_create_jira_ticket_tool_falls_back_to_default_project_key(
    db_session, principal, monkeypatch
):
    monkeypatch.setattr("cerebro.config.settings.jira_default_project_key", "DEFAULT")
    api = MagicMock()
    api.auth.base_url = "https://acme.atlassian.net"
    api.create_issue.return_value = {"id": "1", "key": "DEFAULT-1"}

    TOOLS["create_jira_ticket"].handler(
        session=db_session, principal=principal, summary="x", api=api
    )

    assert api.create_issue.call_args.args[0] == "DEFAULT"


def test_jira_issue_status_tool(db_session, principal):
    api = MagicMock()
    api.get_issue.return_value = {
        "fields": {"summary": "Fix bug", "status": {"name": "In Progress"}}
    }

    result = TOOLS["jira_issue_status"].handler(
        session=db_session, principal=principal, issue_key="PROJ-1", api=api
    )

    assert result["status"] == "In Progress"
    assert result["summary"] == "Fix bug"
