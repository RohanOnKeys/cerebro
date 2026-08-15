"""0016_admin_dashboard_mutations

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-15

Adds the schema the team dashboard's write endpoints need (Settings page,
Danger Zone, Members Approve/Reject already had a home in role_claims):

- orgs.admin_contact / orgs.billing_tier: plain display fields for the
  Settings page's Organization Details panel. Nullable — a fresh org has
  neither set until an admin fills them in.
- orgs.channels_active / orgs.workspace_active: the two Danger Zone
  actions ("revoke access for a connected integration" / "deactivate this
  workspace's integration entirely") flip these. Both default true. Note
  in the admin router docstring: nothing else in this codebase reads these
  flags yet to actually gate channel behavior (the caspian-sdk channel
  gateway runs as a separate process with no knowledge of this DB column) —
  this records real, persisted administrative intent, not a live kill
  switch, until that wiring exists.
- notification_preferences: org-scoped rows for the Settings page's
  Notification Preferences panel. Seeded lazily by the router on first
  read rather than in this migration, so the default set can change
  without a new migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orgs", sa.Column("admin_contact", sa.String(), nullable=True))
    op.add_column("orgs", sa.Column("billing_tier", sa.String(), nullable=True))
    op.add_column(
        "orgs",
        sa.Column("channels_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "orgs",
        sa.Column("workspace_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_preferences_org_id", "notification_preferences", ["org_id"]
    )
    op.create_index(
        "ix_notification_preferences_org_id_key",
        "notification_preferences",
        ["org_id", "key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_preferences_org_id_key", table_name="notification_preferences"
    )
    op.drop_index(
        "ix_notification_preferences_org_id", table_name="notification_preferences"
    )
    op.drop_table("notification_preferences")

    op.drop_column("orgs", "workspace_active")
    op.drop_column("orgs", "channels_active")
    op.drop_column("orgs", "billing_tier")
    op.drop_column("orgs", "admin_contact")
