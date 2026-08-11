"""0006_meetings

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("organizer_principal_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["organizer_principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_org_id", "meetings", ["org_id"])
    op.create_index("ix_meetings_starts_at", "meetings", ["starts_at"])
    op.create_index("ix_meetings_status", "meetings", ["status"])

    op.create_table(
        "meeting_attendees",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("meeting_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("rsvp_status", sa.String(), nullable=False),
        sa.Column("reminder_stage", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meeting_attendees_meeting_id", "meeting_attendees", ["meeting_id"])
    op.create_index(
        "ix_meeting_attendees_principal_id", "meeting_attendees", ["principal_id"]
    )
    op.create_index(
        "ix_meeting_attendees_meeting_id_principal_id",
        "meeting_attendees",
        ["meeting_id", "principal_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meeting_attendees_meeting_id_principal_id", table_name="meeting_attendees"
    )
    op.drop_index("ix_meeting_attendees_principal_id", table_name="meeting_attendees")
    op.drop_index("ix_meeting_attendees_meeting_id", table_name="meeting_attendees")
    op.drop_table("meeting_attendees")

    op.drop_index("ix_meetings_status", table_name="meetings")
    op.drop_index("ix_meetings_starts_at", table_name="meetings")
    op.drop_index("ix_meetings_org_id", table_name="meetings")
    op.drop_table("meetings")
