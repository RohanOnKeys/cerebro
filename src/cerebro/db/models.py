from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class TaskStatus(str, Enum):
    OPEN = "open"
    ACKED = "acked"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class LadderStatus(str, Enum):
    ACTIVE = "active"
    ACKED = "acked"
    CANCELLED = "cancelled"
    EXHAUSTED = "exhausted"


class MeetingStatus(str, Enum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class RSVPStatus(str, Enum):
    PENDING = "pending"
    YES = "yes"
    NO = "no"


class ReminderStage(str, Enum):
    NONE = "none"
    T_MINUS_24H = "t_minus_24h"
    T_MINUS_60M = "t_minus_60m"
    T_MINUS_10M = "t_minus_10m"


class Population(str, Enum):
    CLIENT = "client"
    OPS = "ops"
    DEV = "dev"
    LEAD = "lead"
    ADMIN = "admin"


class OrderStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class GapChaseStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    EXHAUSTED = "exhausted"


class NudgeKind(str, Enum):
    GAP_ASK = "gap_ask"
    GAP_ESCALATE = "gap_escalate"
    TASK_CARD = "task_card"
    TASK_LADDER = "task_ladder"
    TASK_BLOCKED = "task_blocked"
    MEETING_REMINDER = "meeting_reminder"
    SUMMARY_REQUEST = "summary_request"
    SUMMARY_CHASE = "summary_chase"


class NudgeStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Org(Base):
    __tablename__ = "orgs"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    principals = relationship("Principal", back_populates="org")
    orders = relationship("Order", back_populates="org")


class Principal(Base):
    __tablename__ = "principals"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    population = Column(SQLEnum(Population), nullable=False)
    email = Column(String)
    skills_json = Column(String, nullable=False, default="[]")
    wip_cap = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    org = relationship("Org", back_populates="principals")
    bindings = relationship("ChannelBinding", back_populates="principal")
    orders = relationship("Order", back_populates="principal")

    __table_args__ = (
        Index("ix_principals_org_id", "org_id"),
        Index("ix_principals_population", "population"),
    )


class ChannelBinding(Base):
    __tablename__ = "channel_bindings"

    id = Column(String, primary_key=True)
    principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    channel = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    conversation_id = Column(String)
    verified = Column(String, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    principal = relationship("Principal", back_populates="bindings")

    __table_args__ = (
        Index("ix_channel_bindings_principal_id", "principal_id"),
        Index("ix_channel_bindings_channel_channel_id", "channel", "channel_id"),
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    order_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default=OrderStatus.OPEN.value)
    free_text = Column(String)
    fields_json = Column(String, nullable=False, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    org = relationship("Org", back_populates="orders")
    principal = relationship("Principal", back_populates="orders")
    gap_chases = relationship("GapChase", back_populates="order")

    __table_args__ = (
        Index("ix_orders_org_id", "org_id"),
        Index("ix_orders_principal_id", "principal_id"),
        Index("ix_orders_order_type", "order_type"),
        Index("ix_orders_status", "status"),
    )


class FieldSpec(Base):
    __tablename__ = "field_specs"

    id = Column(String, primary_key=True)
    order_type = Column(String, nullable=False)
    field_name = Column(String, nullable=False)
    required = Column(Boolean, nullable=False, default=True)
    validator = Column(String, nullable=False, default="nonempty")

    __table_args__ = (Index("ix_field_specs_order_type", "order_type"),)


class GapChase(Base):
    __tablename__ = "gap_chases"

    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    field_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default=GapChaseStatus.OPEN.value)
    ask_count = Column(Integer, nullable=False, default=0)
    last_asked_at = Column(DateTime)
    next_ask_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    order = relationship("Order", back_populates="gap_chases")
    nudges = relationship("Nudge", back_populates="gap_chase")

    __table_args__ = (
        Index("ix_gap_chases_order_id", "order_id"),
        Index("ix_gap_chases_status", "status"),
    )


class Nudge(Base):
    __tablename__ = "nudges"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    order_id = Column(String, ForeignKey("orders.id"))
    gap_chase_id = Column(String, ForeignKey("gap_chases.id"))
    kind = Column(String, nullable=False)
    body = Column(String, nullable=False)
    status = Column(String, nullable=False, default=NudgeStatus.PENDING.value)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    sent_at = Column(DateTime)

    gap_chase = relationship("GapChase", back_populates="nudges")

    __table_args__ = (
        Index("ix_nudges_org_id", "org_id"),
        Index("ix_nudges_principal_id", "principal_id"),
        Index("ix_nudges_order_id", "order_id"),
        Index("ix_nudges_status", "status"),
        Index("ix_nudges_kind", "kind"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    order_id = Column(String, ForeignKey("orders.id"))
    number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String)
    designation = Column(String, nullable=False)
    required_skills_json = Column(String, nullable=False, default="[]")
    status = Column(String, nullable=False, default=TaskStatus.OPEN.value)
    assignee_principal_id = Column(String, ForeignKey("principals.id"))
    blocked_reason = Column(String)
    ladder_rung = Column(Integer, nullable=False, default=0)
    ladder_status = Column(String, nullable=False, default=LadderStatus.ACTIVE.value)
    ladder_last_fired_at = Column(DateTime)
    ladder_next_due_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    acked_at = Column(DateTime)

    __table_args__ = (
        Index("ix_tasks_org_id", "org_id"),
        Index("ix_tasks_order_id", "order_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_assignee_principal_id", "assignee_principal_id"),
        Index("ix_tasks_org_id_number", "org_id", "number", unique=True),
    )


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    organizer_principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    title = Column(String, nullable=False)
    starts_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=30)
    status = Column(String, nullable=False, default=MeetingStatus.SCHEDULED.value)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    attendees = relationship("MeetingAttendee", back_populates="meeting")

    __table_args__ = (
        Index("ix_meetings_org_id", "org_id"),
        Index("ix_meetings_starts_at", "starts_at"),
        Index("ix_meetings_status", "status"),
    )


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"

    id = Column(String, primary_key=True)
    meeting_id = Column(String, ForeignKey("meetings.id"), nullable=False)
    principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    rsvp_status = Column(String, nullable=False, default=RSVPStatus.PENDING.value)
    reminder_stage = Column(String, nullable=False, default=ReminderStage.NONE.value)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    meeting = relationship("Meeting", back_populates="attendees")

    __table_args__ = (
        Index("ix_meeting_attendees_meeting_id", "meeting_id"),
        Index("ix_meeting_attendees_principal_id", "principal_id"),
        Index(
            "ix_meeting_attendees_meeting_id_principal_id",
            "meeting_id",
            "principal_id",
            unique=True,
        ),
    )


class SummaryEntry(Base):
    __tablename__ = "summary_entries"

    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    text = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        Index("ix_summary_entries_order_id", "order_id"),
        Index("ix_summary_entries_principal_id", "principal_id"),
    )


class Message(Base):
    """Persisted conversation ledger: one row per user/assistant turn."""

    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    channel = Column(String, nullable=False)
    # Population snapshotted at send time (not re-joined from principals),
    # so history reads stay correct even if a principal's population changes later.
    population = Column(String, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        Index("ix_messages_principal_id_created_at", "principal_id", "created_at"),
        Index("ix_messages_org_id", "org_id"),
    )
