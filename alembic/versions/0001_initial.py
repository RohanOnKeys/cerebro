"""0001_initial

Revision ID: 0001
Revises:
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "principals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column(
            "population",
            sa.Enum("CLIENT", "OPS", "DEV", "LEAD", "ADMIN", name="population"),
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_principals_org_id", "principals", ["org_id"])
    op.create_index("ix_principals_population", "principals", ["population"])

    op.create_table(
        "channel_bindings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("verified", sa.String(), nullable=True, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_channel_bindings_principal_id", "channel_bindings", ["principal_id"]
    )
    op.create_index(
        "ix_channel_bindings_channel_channel_id",
        "channel_bindings",
        ["channel", "channel_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_bindings_channel_channel_id", table_name="channel_bindings")
    op.drop_index("ix_channel_bindings_principal_id", table_name="channel_bindings")
    op.drop_table("channel_bindings")

    op.drop_index("ix_principals_population", table_name="principals")
    op.drop_index("ix_principals_org_id", table_name="principals")
    op.drop_table("principals")

    op.drop_table("orgs")
