from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


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

    __table_args__ = (
        Index("ix_gap_chases_order_id", "order_id"),
        Index("ix_gap_chases_status", "status"),
    )
