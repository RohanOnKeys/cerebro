"""0015_principal_display_name

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-14

Adds a nullable display_name to principals. The dashboard's Members panel
needs a human name to show; today Principal only has `email`. Nullable and
additive only — no existing row, query, or code path changes behavior.
Falls back to email in the API layer when null, so this is safe to deploy
before every principal has been backfilled with a name.

Note: Meeting conferencing already exists as provider/join_url (0014), so
the patch's 0015_meeting_conferencing migration is intentionally omitted.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("principals", sa.Column("display_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("principals", "display_name")
