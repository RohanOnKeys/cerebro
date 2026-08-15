"""Org lookup/creation by a short, human-typeable join code.

The onboarding flow (ingress/enrollment.py) asks every unrecognized sender
for this code before anything else: it routes them to the right org, or —
if the code doesn't match anything yet — mints a brand-new org for it. That
"create if unrecognized" choice mirrors this codebase's existing bootstrap
philosophy (see the auto-create-org-on-first-enrollment fix from Phase 0),
not a strict pre-shared-secret gate: a mistyped code doesn't lock anyone
out, it just starts (or joins) a different team than intended.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from cerebro.db.models import Org

# Excludes 0/O and 1/I so a code read aloud or typed on a phone keyboard
# doesn't collide on ambiguous characters.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6


def generate_join_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def resolve_or_create_org_by_code(session: Session, code: str) -> tuple[Org, bool]:
    """Look up an org by its join code. If none matches, create one with
    that code. Returns (org, created)."""
    normalized = normalize_code(code)
    org = session.query(Org).filter(Org.join_code == normalized).first()
    if org is not None:
        return org, False

    org = Org(
        id=str(uuid.uuid4()),
        name=f"Team {normalized}",
        join_code=normalized,
        created_at=datetime.now(UTC),
    )
    session.add(org)
    session.commit()
    return org, True
