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

from sqlalchemy import select
from sqlalchemy.orm import Session

from cerebro.db.models import Message, Org

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


def resolve_active_org(session: Session) -> Org | None:
    """The org actually live in the channels right now: the org behind the
    most recent Message, falling back to the most recently created org.
    Returns None only if no org exists at all yet.

    This exists because both the admin dashboard and the GitHub webhook
    handler used to assume a single, hardcoded org (the dashboard read the
    literal first-ever-created row; the webhook read a GITHUB_DEFAULT_ORG_ID
    config default of "default_org"). Once real orgs get created through the
    join-code enrollment flow, neither assumption holds - the webhook path
    started throwing a ForeignKeyViolation on every event because no org
    named "default_org" actually existed in the database."""
    latest_active_org_id = session.scalar(
        select(Message.org_id).order_by(Message.created_at.desc()).limit(1)
    )
    if latest_active_org_id is not None:
        org = session.get(Org, latest_active_org_id)
        if org is not None:
            return org

    return session.query(Org).order_by(Org.created_at.desc()).first()
