"""Per-class teaching context reused across technique search."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User

CLASS_FORMATS = ("lecture", "lab", "online", "hybrid")
CLASS_STATUSES = ("planned", "active", "archived")


class ClassProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "class_profiles"

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'planned'")
    )

    # Planned profiles may use ranges; active profiles prefer concrete size.
    class_size: Mapped[int | None] = mapped_column(Integer)
    class_size_min: Mapped[int | None] = mapped_column(Integer)
    class_size_max: Mapped[int | None] = mapped_column(Integer)

    student_background: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)
    class_length_minutes: Mapped[int | None] = mapped_column(Integer)
    technology: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    teacher: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "format IN ('lecture', 'lab', 'online', 'hybrid')",
            name="class_profile_format",
        ),
        CheckConstraint(
            "status IN ('planned', 'active', 'archived')",
            name="class_profile_status",
        ),
        CheckConstraint(
            "class_size IS NULL OR class_size > 0",
            name="class_profile_size_positive",
        ),
        CheckConstraint(
            "class_size_min IS NULL OR class_size_min > 0",
            name="class_profile_size_min_positive",
        ),
        CheckConstraint(
            "class_size_max IS NULL OR class_size_max > 0",
            name="class_profile_size_max_positive",
        ),
        CheckConstraint(
            "class_size_min IS NULL OR class_size_max IS NULL OR class_size_min <= class_size_max",
            name="class_profile_size_range_order",
        ),
        CheckConstraint(
            "class_length_minutes IS NULL OR class_length_minutes > 0",
            name="class_profile_length_positive",
        ),
        Index("ix_class_profiles_teacher_id", "teacher_id"),
        Index("ix_class_profiles_status", "status"),
        Index("ix_class_profiles_subject", "subject"),
    )

    def effective_class_size(self) -> float | None:
        if self.class_size is not None:
            return float(self.class_size)
        if self.class_size_min is not None and self.class_size_max is not None:
            return (self.class_size_min + self.class_size_max) / 2.0
        return float(self.class_size_min or self.class_size_max) if (
            self.class_size_min or self.class_size_max
        ) else None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClassProfile {self.title!r} status={self.status}>"
