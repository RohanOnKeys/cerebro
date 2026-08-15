"""0017_org_join_codes_and_staged_enrollment

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-15

Every onboarding channel now asks for a team (org) code before asking
client-vs-team, so a sender can be routed to the right org instead of
everyone landing in one hardcoded default_org. Two schema changes:

- orgs.join_code: a short, unique, human-typeable code. Backfilled for any
  org that already exists (there's exactly one in most deployments so
  far, "default_org") so existing teams get a real code to start handing
  out rather than being stuck on the old implicit single-org behavior.
- pending_enrollments: org_id becomes nullable (the org isn't known until
  the code is answered) and gains a `stage` column ("awaiting_code" then
  "awaiting_usertype") so handle_unknown_sender knows which question a
  reply is answering.
"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no O/0, I/1 confusion


def _generate_join_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def upgrade() -> None:
    op.add_column("orgs", sa.Column("join_code", sa.String(), nullable=True))

    # Backfill: every existing org needs a real code before the column can
    # be made unique + NOT NULL.
    bind = op.get_bind()
    orgs_table = sa.table("orgs", sa.column("id", sa.String), sa.column("join_code", sa.String))
    existing_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM orgs"))]
    seen_codes: set[str] = set()
    for org_id in existing_ids:
        code = _generate_join_code()
        while code in seen_codes:
            code = _generate_join_code()
        seen_codes.add(code)
        bind.execute(
            orgs_table.update().where(orgs_table.c.id == org_id).values(join_code=code)
        )

    op.alter_column("orgs", "join_code", nullable=False)
    op.create_index("ix_orgs_join_code", "orgs", ["join_code"], unique=True)

    op.add_column(
        "pending_enrollments",
        sa.Column("stage", sa.String(), nullable=False, server_default="awaiting_code"),
    )
    op.alter_column("pending_enrollments", "org_id", nullable=True)


def downgrade() -> None:
    op.alter_column("pending_enrollments", "org_id", nullable=False)
    op.drop_column("pending_enrollments", "stage")

    op.drop_index("ix_orgs_join_code", table_name="orgs")
    op.drop_column("orgs", "join_code")
