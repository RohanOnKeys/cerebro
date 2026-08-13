"""0014_role_claims_and_meeting_providers

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings", sa.Column("provider", sa.String(), nullable=False, server_default="")
    )
    op.add_column("meetings", sa.Column("join_url", sa.String(), nullable=True))
    op.add_column("meetings", sa.Column("external_event_id", sa.String(), nullable=True))

    op.create_table(
        "role_claims",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("claimant_principal_id", sa.String(), nullable=False),
        sa.Column("requested_population", sa.String(), nullable=False),
        sa.Column("approver_principal_id", sa.String(), nullable=True),
        sa.Column("nonce", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["claimant_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["approver_principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_role_claims_nonce", "role_claims", ["nonce"], unique=True)
    op.create_index(
        "ix_role_claims_status_expires_at", "role_claims", ["status", "expires_at"]
    )
    op.create_index("ix_role_claims_org_id", "role_claims", ["org_id"])
    op.create_index(
        "ix_role_claims_claimant_principal_id", "role_claims", ["claimant_principal_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_role_claims_claimant_principal_id", table_name="role_claims")
    op.drop_index("ix_role_claims_org_id", table_name="role_claims")
    op.drop_index("ix_role_claims_status_expires_at", table_name="role_claims")
    op.drop_index("ix_role_claims_nonce", table_name="role_claims")
    op.drop_table("role_claims")

    op.drop_column("meetings", "external_event_id")
    op.drop_column("meetings", "join_url")
    op.drop_column("meetings", "provider")
