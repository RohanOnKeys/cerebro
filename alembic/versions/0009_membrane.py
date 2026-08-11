"""0009_membrane

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-11

"""
import json
import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Six crossing rules: what happens when content moves source -> target.
# Outbound-to-client is redacted or denied by default (fail closed); inbound
# from a client to the team that can act on it is allowed unredacted.
SEED_POLICIES: tuple[tuple[str, str, str, list[str]], ...] = (
    ("dev", "client", "redact", ["stack_trace", "estimate"]),
    ("ops", "client", "redact", ["estimate"]),
    ("lead", "client", "redact", ["estimate", "risk"]),
    ("admin", "client", "deny", []),
    ("client", "dev", "allow", []),
    ("client", "ops", "allow", []),
)


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_population", sa.String(), nullable=False),
        sa.Column("target_population", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("redact_fields_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policies_source_target",
        "policies",
        ["source_population", "target_population"],
        unique=True,
    )

    op.create_table(
        "crossings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("source_population", sa.String(), nullable=False),
        sa.Column("target_population", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("content_ref", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crossings_org_id", "crossings", ["org_id"])
    op.create_index("ix_crossings_principal_id", "crossings", ["principal_id"])
    op.create_index("ix_crossings_created_at", "crossings", ["created_at"])

    policies_table = sa.table(
        "policies",
        sa.column("id", sa.String),
        sa.column("source_population", sa.String),
        sa.column("target_population", sa.String),
        sa.column("action", sa.String),
        sa.column("redact_fields_json", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        policies_table,
        [
            {
                "id": str(uuid.uuid4()),
                "source_population": source,
                "target_population": target,
                "action": action,
                "redact_fields_json": json.dumps(redact_fields),
                "created_at": now,
            }
            for source, target, action, redact_fields in SEED_POLICIES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_crossings_created_at", table_name="crossings")
    op.drop_index("ix_crossings_principal_id", table_name="crossings")
    op.drop_index("ix_crossings_org_id", table_name="crossings")
    op.drop_table("crossings")

    op.drop_index("ix_policies_source_target", table_name="policies")
    op.drop_table("policies")
