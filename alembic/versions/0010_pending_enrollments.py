"""0010_pending_enrollments

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_enrollments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pending_enrollments_channel_channel_id",
        "pending_enrollments",
        ["channel", "channel_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_enrollments_channel_channel_id", table_name="pending_enrollments"
    )
    op.drop_table("pending_enrollments")
