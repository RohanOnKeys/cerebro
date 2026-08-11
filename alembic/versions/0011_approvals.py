"""0011_approvals

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("nonce", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("payload_json", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_nonce", "approvals", ["nonce"], unique=True)
    op.create_index(
        "ix_approvals_state_expires_at",
        "approvals",
        ["state", "expires_at"],
    )
    op.create_index("ix_approvals_org_id", "approvals", ["org_id"])
    op.create_index("ix_approvals_principal_id", "approvals", ["principal_id"])


def downgrade() -> None:
    op.drop_index("ix_approvals_principal_id", table_name="approvals")
    op.drop_index("ix_approvals_org_id", table_name="approvals")
    op.drop_index("ix_approvals_state_expires_at", table_name="approvals")
    op.drop_index("ix_approvals_nonce", table_name="approvals")
    op.drop_table("approvals")
