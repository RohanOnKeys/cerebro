"""schedule_meeting/cancel_meeting provider dispatch: none (default), meet, zoom."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cerebro.db.models import Base, Meeting, Org, Population, Principal
from cerebro.registry import TOOLS


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


@pytest.fixture
def organizer(db_session):
    principal = Principal(
        id="p_organizer",
        org_id="org_1",
        population=Population.DEV,
        email="organizer@acme.com",
        created_at=datetime.now(UTC),
    )
    db_session.add(principal)
    db_session.commit()
    return principal


def test_default_provider_none_behavior_unchanged(db_session, organizer):
    """provider omitted keeps today's DB-only behavior; no external client touched."""
    gcal_client = MagicMock()
    zoom_client = MagicMock()

    result = TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        gcal_client=gcal_client,
        zoom_client=zoom_client,
    )

    assert result["provider"] == ""
    assert result["join_url"] == ""
    gcal_client.free_busy.assert_not_called()
    gcal_client.create_event.assert_not_called()
    zoom_client.create_meeting.assert_not_called()


def test_meet_provider_threads_free_busy_into_find_slot(db_session, organizer):
    """provider='meet' actually uses a non-empty busy list, not a hardcoded []."""
    gcal_client = MagicMock()
    busy_until = datetime.now(UTC) + timedelta(hours=1)
    gcal_client.free_busy.return_value = [(datetime.now(UTC), busy_until)]
    gcal_client.create_event.return_value = {
        "event_id": "evt_1",
        "meet_link": "https://meet.google.com/abc-defg-hij",
        "html_link": "https://calendar.google.com/evt_1",
    }

    result = TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="meet",
        gcal_client=gcal_client,
    )

    gcal_client.free_busy.assert_called_once()
    assert result["provider"] == "meet"
    assert result["join_url"] == "https://meet.google.com/abc-defg-hij"
    meeting = db_session.query(Meeting).filter(Meeting.id == result["id"]).one()
    assert meeting.external_event_id == "evt_1"


def test_meet_provider_with_explicit_starts_at_skips_free_busy(db_session, organizer):
    """An explicit starts_at means no availability check is needed."""
    gcal_client = MagicMock()
    gcal_client.create_event.return_value = {
        "event_id": "evt_2",
        "meet_link": "https://meet.google.com/xyz",
        "html_link": "",
    }

    TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="meet",
        starts_at="2026-08-20T09:00:00+00:00",
        gcal_client=gcal_client,
    )

    gcal_client.free_busy.assert_not_called()
    gcal_client.create_event.assert_called_once()


def test_meet_provider_error_returns_error_dict(db_session, organizer):
    from cerebro.gcal.api import GoogleCalendarAPIError

    gcal_client = MagicMock()
    gcal_client.free_busy.side_effect = GoogleCalendarAPIError("boom")

    result = TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="meet",
        gcal_client=gcal_client,
    )

    assert result["error"] == "gcal_error"
    assert db_session.query(Meeting).count() == 0


def test_zoom_provider_creates_real_meeting(db_session, organizer, monkeypatch):
    monkeypatch.setattr("cerebro.registry.settings.zoom_user_id", "organizer@acme.com")
    zoom_client = MagicMock()
    zoom_client.create_meeting.return_value = {
        "meeting_id": 123456789,
        "join_url": "https://zoom.us/j/123456789",
        "start_url": "https://zoom.us/s/123456789",
    }

    result = TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="zoom",
        starts_at="2026-08-20T09:00:00+00:00",
        zoom_client=zoom_client,
    )

    assert result["provider"] == "zoom"
    assert result["join_url"] == "https://zoom.us/j/123456789"
    meeting = db_session.query(Meeting).filter(Meeting.id == result["id"]).one()
    assert meeting.external_event_id == "123456789"


def test_zoom_provider_never_checks_availability(db_session, organizer, monkeypatch):
    """No calendar concept for Zoom: no free/busy call happens for this provider."""
    monkeypatch.setattr("cerebro.registry.settings.zoom_user_id", "organizer@acme.com")
    gcal_client = MagicMock()
    zoom_client = MagicMock()
    zoom_client.create_meeting.return_value = {
        "meeting_id": 1,
        "join_url": "https://zoom.us/j/1",
        "start_url": "",
    }

    TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="zoom",
        starts_at="2026-08-20T09:00:00+00:00",
        gcal_client=gcal_client,
        zoom_client=zoom_client,
    )

    gcal_client.free_busy.assert_not_called()


def test_zoom_provider_missing_user_id_errors(db_session, organizer, monkeypatch):
    monkeypatch.setattr("cerebro.registry.settings.zoom_user_id", "")

    result = TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="zoom",
        starts_at="2026-08-20T09:00:00+00:00",
        zoom_client=MagicMock(),
    )

    assert result["error"] == "missing_zoom_user_id"
    assert db_session.query(Meeting).count() == 0


def test_cancel_meeting_deletes_real_meet_event_before_cancelling(db_session, organizer):
    gcal_client = MagicMock()
    gcal_client.create_event.return_value = {
        "event_id": "evt_9",
        "meet_link": "https://meet.google.com/xyz",
        "html_link": "",
    }
    scheduled = TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="meet",
        starts_at="2026-08-20T09:00:00+00:00",
        gcal_client=gcal_client,
    )

    result = TOOLS["cancel_meeting"].handler(
        session=db_session,
        principal=organizer,
        meeting_id=scheduled["id"],
        gcal_client=gcal_client,
    )

    gcal_client.delete_event.assert_called_once()
    assert result["status"] == "cancelled"


def test_cancel_meeting_gcal_error_leaves_row_untouched(db_session, organizer):
    from cerebro.gcal.api import GoogleCalendarAPIError

    gcal_client = MagicMock()
    gcal_client.create_event.return_value = {
        "event_id": "evt_10",
        "meet_link": "https://meet.google.com/xyz",
        "html_link": "",
    }
    scheduled = TOOLS["schedule_meeting"].handler(
        session=db_session,
        principal=organizer,
        title="Standup",
        provider="meet",
        starts_at="2026-08-20T09:00:00+00:00",
        gcal_client=gcal_client,
    )

    gcal_client.delete_event.side_effect = GoogleCalendarAPIError("boom")
    result = TOOLS["cancel_meeting"].handler(
        session=db_session,
        principal=organizer,
        meeting_id=scheduled["id"],
        gcal_client=gcal_client,
    )

    assert result["error"] == "gcal_error"
    meeting = db_session.query(Meeting).filter(Meeting.id == scheduled["id"]).one()
    assert meeting.status == "scheduled"
