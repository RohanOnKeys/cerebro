"""0018_reminders

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-15

Self-hosted reminder/deadline system: no external calendar dependency
(distinct from the GCal/Zoom meeting-provider integration in 0014).
`kind` distinguishes a general team reminder from a client-requested
deadline; both are fired the same way by the new clock job in
services/reminders.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("created_by_principal_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("fired_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reminders_org_id", "reminders", ["org_id"])
    op.create_index("ix_reminders_principal_id", "reminders", ["principal_id"])
    op.create_index("ix_reminders_order_id", "reminders", ["order_id"])
    op.create_index(
        "ix_reminders_status_due_at", "reminders", ["status", "due_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_reminders_status_due_at", table_name="reminders")
    op.drop_index("ix_reminders_order_id", table_name="reminders")
    op.drop_index("ix_reminders_principal_id", table_name="reminders")
    op.drop_index("ix_reminders_org_id", table_name="reminders")
    op.drop_table("reminders")
