import pytest

from cerebro.ingress.dedupe import dedupe, clear_dedupe


@pytest.fixture(autouse=True)
def cleanup():
    """Clear dedupe cache before each test."""
    clear_dedupe()
    yield
    clear_dedupe()


def test_dedupe_first_occurrence():
    """First occurrence of an ID should return True."""
    assert dedupe("msg_123") is True


def test_dedupe_duplicate():
    """Second occurrence of the same ID should return False."""
    dedupe("msg_123")
    assert dedupe("msg_123") is False


def test_dedupe_multiple_ids():
    """Different IDs should all return True on first occurrence."""
    assert dedupe("msg_1") is True
    assert dedupe("msg_2") is True
    assert dedupe("msg_3") is True


def test_dedupe_sequence():
    """Same ID twice should return True then False."""
    msg_id = "msg_456"
    first = dedupe(msg_id)
    second = dedupe(msg_id)

    assert first is True
    assert second is False
