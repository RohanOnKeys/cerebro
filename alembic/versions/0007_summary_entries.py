"""0007_summary_entries

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "summary_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_summary_entries_order_id", "summary_entries", ["order_id"])
    op.create_index(
        "ix_summary_entries_principal_id", "summary_entries", ["principal_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_summary_entries_principal_id", table_name="summary_entries")
    op.drop_index("ix_summary_entries_order_id", table_name="summary_entries")
    op.drop_table("summary_entries")
