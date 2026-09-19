"""Connection requests between educators."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ConnectionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class Connection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "connections"

    requester_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="connection_status", values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        default=ConnectionStatus.PENDING,
    )

    requester = relationship("User", foreign_keys=[requester_id], lazy="joined")
    receiver = relationship("User", foreign_keys=[receiver_id], lazy="joined")

    __table_args__ = (
        UniqueConstraint("requester_id", "receiver_id", name="uq_connections_pair"),
        CheckConstraint("requester_id <> receiver_id", name="no_self_connection"),
        Index("ix_connections_requester_id", "requester_id"),
        Index("ix_connections_receiver_id", "receiver_id"),
        Index("ix_connections_status", "status"),
    )
