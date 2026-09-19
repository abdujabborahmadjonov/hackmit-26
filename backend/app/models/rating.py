"""Peer/student ratings left on a teacher."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Rating(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ratings"

    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    is_verified_student: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    reviewer = relationship("User", foreign_keys=[reviewer_id], lazy="joined")

    __table_args__ = (
        # One review per (reviewer, teacher); updating replaces the old score.
        UniqueConstraint("reviewer_id", "teacher_id", name="uq_ratings_reviewer_teacher"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range"),
        CheckConstraint("reviewer_id <> teacher_id", name="no_self_rating"),
        Index("ix_ratings_teacher_id", "teacher_id"),
        Index("ix_ratings_reviewer_id", "reviewer_id"),
    )
