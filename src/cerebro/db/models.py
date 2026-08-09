from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Population(str, Enum):
    CLIENT = "client"
    OPS = "ops"
    DEV = "dev"
    LEAD = "lead"
    ADMIN = "admin"


class Org(Base):
    __tablename__ = "orgs"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    principals = relationship("Principal", back_populates="org")


class Principal(Base):
    __tablename__ = "principals"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("orgs.id"), nullable=False)
    population = Column(SQLEnum(Population), nullable=False)
    email = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    org = relationship("Org", back_populates="principals")
    bindings = relationship("ChannelBinding", back_populates="principal")

    __table_args__ = (
        Index("ix_principals_org_id", "org_id"),
        Index("ix_principals_population", "population"),
    )


class ChannelBinding(Base):
    __tablename__ = "channel_bindings"

    id = Column(String, primary_key=True)
    principal_id = Column(String, ForeignKey("principals.id"), nullable=False)
    channel = Column(String, nullable=False)  # telegram, slack, discord, email, whatsapp
    channel_id = Column(String, nullable=False)  # user's phone, email, slack id, etc
    conversation_id = Column(String)  # enrollment conversation id
    verified = Column(String, default="pending")  # pending, verified
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    principal = relationship("Principal", back_populates="bindings")

    __table_args__ = (
        Index("ix_channel_bindings_principal_id", "principal_id"),
        Index("ix_channel_bindings_channel_channel_id", "channel", "channel_id"),
    )
