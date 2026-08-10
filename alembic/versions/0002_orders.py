"""0002_orders

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("order_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("free_text", sa.String(), nullable=True),
        sa.Column("fields_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_org_id", "orders", ["org_id"])
    op.create_index("ix_orders_principal_id", "orders", ["principal_id"])
    op.create_index("ix_orders_order_type", "orders", ["order_type"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "field_specs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("order_type", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("validator", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_field_specs_order_type", "field_specs", ["order_type"])

    op.create_table(
        "gap_chases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("ask_count", sa.Integer(), nullable=False),
        sa.Column("last_asked_at", sa.DateTime(), nullable=True),
        sa.Column("next_ask_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gap_chases_order_id", "gap_chases", ["order_id"])
    op.create_index("ix_gap_chases_status", "gap_chases", ["status"])


def downgrade() -> None:
    op.drop_index("ix_gap_chases_status", table_name="gap_chases")
    op.drop_index("ix_gap_chases_order_id", table_name="gap_chases")
    op.drop_table("gap_chases")

    op.drop_index("ix_field_specs_order_type", table_name="field_specs")
    op.drop_table("field_specs")

    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_order_type", table_name="orders")
    op.drop_index("ix_orders_principal_id", table_name="orders")
    op.drop_index("ix_orders_org_id", table_name="orders")
    op.drop_table("orders")
