"""0004_nudges

Revision ID: 0004
Revises: 0002
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nudges",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("gap_chase_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["gap_chase_id"], ["gap_chases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nudges_org_id", "nudges", ["org_id"])
    op.create_index("ix_nudges_principal_id", "nudges", ["principal_id"])
    op.create_index("ix_nudges_order_id", "nudges", ["order_id"])
    op.create_index("ix_nudges_status", "nudges", ["status"])
    op.create_index("ix_nudges_kind", "nudges", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_nudges_kind", table_name="nudges")
    op.drop_index("ix_nudges_status", table_name="nudges")
    op.drop_index("ix_nudges_order_id", table_name="nudges")
    op.drop_index("ix_nudges_principal_id", table_name="nudges")
    op.drop_index("ix_nudges_org_id", table_name="nudges")
    op.drop_table("nudges")
