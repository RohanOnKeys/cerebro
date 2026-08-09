from typing import Dict, Set

# Track seen IDs within a time window
_seen_ids: Set[str] = set()


def dedupe(message_id: str) -> bool:
    """Return True if this message_id is first occurrence, False if duplicate."""
    if message_id in _seen_ids:
        return False
    _seen_ids.add(message_id)
    return True


def clear_dedupe() -> None:
    """Clear the deduplication cache (for testing)."""
    _seen_ids.clear()
