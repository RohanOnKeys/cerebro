"""0012_ci_runs

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ci_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("github_run_id", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("workflow_name", sa.String(), nullable=False),
        sa.Column("head_branch", sa.String(), nullable=False),
        sa.Column("head_sha", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("conclusion", sa.String(), nullable=True),
        sa.Column("html_url", sa.String(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("requested_by_principal_id", sa.String(), nullable=True),
        sa.Column("failure_summary", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["requested_by_principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ci_runs_org_id_github_run_id",
        "ci_runs",
        ["org_id", "github_run_id"],
        unique=True,
    )
    op.create_index("ix_ci_runs_org_id", "ci_runs", ["org_id"])
    op.create_index("ix_ci_runs_status", "ci_runs", ["status"])
    op.create_index("ix_ci_runs_conclusion", "ci_runs", ["conclusion"])


def downgrade() -> None:
    op.drop_index("ix_ci_runs_conclusion", table_name="ci_runs")
    op.drop_index("ix_ci_runs_status", table_name="ci_runs")
    op.drop_index("ix_ci_runs_org_id", table_name="ci_runs")
    op.drop_index("ix_ci_runs_org_id_github_run_id", table_name="ci_runs")
    op.drop_table("ci_runs")
