"""0005_tasks

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "principals",
        sa.Column("skills_json", sa.String(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "principals",
        sa.Column("wip_cap", sa.Integer(), nullable=False, server_default="3"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("designation", sa.String(), nullable=False),
        sa.Column("required_skills_json", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assignee_principal_id", sa.String(), nullable=True),
        sa.Column("blocked_reason", sa.String(), nullable=True),
        sa.Column("ladder_rung", sa.Integer(), nullable=False),
        sa.Column("ladder_status", sa.String(), nullable=False),
        sa.Column("ladder_last_fired_at", sa.DateTime(), nullable=True),
        sa.Column("ladder_next_due_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("acked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["assignee_principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_org_id", "tasks", ["org_id"])
    op.create_index("ix_tasks_order_id", "tasks", ["order_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_assignee_principal_id", "tasks", ["assignee_principal_id"])
    op.create_index(
        "ix_tasks_org_id_number", "tasks", ["org_id", "number"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_org_id_number", table_name="tasks")
    op.drop_index("ix_tasks_assignee_principal_id", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_order_id", table_name="tasks")
    op.drop_index("ix_tasks_org_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_column("principals", "wip_cap")
    op.drop_column("principals", "skills_json")
