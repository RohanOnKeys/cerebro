"""0013_ci_failures_and_task_link

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ci_runs", sa.Column("task_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_ci_runs_task_id_tasks",
        "ci_runs",
        "tasks",
        ["task_id"],
        ["id"],
    )
    op.create_index("ix_ci_runs_task_id", "ci_runs", ["task_id"])

    op.create_table(
        "ci_failures",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("sample_log", sa.String(), nullable=False),
        sa.Column("triage_json", sa.String(), nullable=False),
        sa.Column("rerun_count_window", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("issue_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ci_failures_org_fingerprint",
        "ci_failures",
        ["org_id", "fingerprint"],
        unique=True,
    )
    op.create_index("ix_ci_failures_org_id", "ci_failures", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_ci_failures_org_id", table_name="ci_failures")
    op.drop_index("ix_ci_failures_org_fingerprint", table_name="ci_failures")
    op.drop_table("ci_failures")
    op.drop_index("ix_ci_runs_task_id", table_name="ci_runs")
    op.drop_constraint("fk_ci_runs_task_id_tasks", "ci_runs", type_="foreignkey")
    op.drop_column("ci_runs", "task_id")
