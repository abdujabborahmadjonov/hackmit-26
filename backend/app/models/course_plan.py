"""Multi-week course plans grounded in existing resources and techniques."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.class_profile import ClassProfile
    from app.models.resource import Resource
    from app.models.technique import Technique
    from app.models.user import User

PLAN_STATUSES = ("draft", "active", "archived")
ITEM_ROLES = ("core", "extension", "assessment")


class CoursePlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_plans"

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    class_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("class_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'draft'")
    )

    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    sessions_per_week: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    goals: Mapped[str | None] = mapped_column(Text)
    overview: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)

    # Snapshot of wizard inputs + retrieval provenance for regenerate.
    generation_inputs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    similar_class_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    teacher: Mapped[User] = relationship(lazy="joined")
    class_profile: Mapped[ClassProfile | None] = relationship(lazy="joined")
    units: Mapped[list[CoursePlanUnit]] = relationship(
        back_populates="course_plan",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CoursePlanUnit.position",
    )

    __table_args__ = (
        CheckConstraint(
            "format IN ('lecture', 'lab', 'online', 'hybrid')",
            name="course_plan_format",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="course_plan_status",
        ),
        CheckConstraint("duration_weeks > 0", name="course_plan_weeks_positive"),
        CheckConstraint(
            "sessions_per_week > 0", name="course_plan_sessions_positive"
        ),
        Index("ix_course_plans_teacher_id", "teacher_id"),
        Index("ix_course_plans_class_profile_id", "class_profile_id"),
        Index("ix_course_plans_status", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CoursePlan {self.title!r} weeks={self.duration_weeks}>"


class CoursePlanUnit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_plan_units"

    course_plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    objectives: Mapped[str | None] = mapped_column(Text)
    concept_labels: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    course_plan: Mapped[CoursePlan] = relationship(back_populates="units")
    sessions: Mapped[list[CoursePlanSession]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CoursePlanSession.position",
    )

    __table_args__ = (
        CheckConstraint("position >= 0", name="course_plan_unit_position"),
        Index("ix_course_plan_units_plan_id", "course_plan_id"),
    )


class CoursePlanSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_plan_sessions"

    unit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_plan_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    focus: Mapped[str | None] = mapped_column(Text)
    activities_summary: Mapped[str | None] = mapped_column(Text)

    unit: Mapped[CoursePlanUnit] = relationship(back_populates="sessions")
    items: Mapped[list[CoursePlanItem]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CoursePlanItem.position",
    )

    __table_args__ = (
        CheckConstraint("position >= 0", name="course_plan_session_position"),
        Index("ix_course_plan_sessions_unit_id", "unit_id"),
    )


class CoursePlanItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_plan_items"

    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_plan_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'core'")
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True,
    )
    technique_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("techniques.id", ondelete="SET NULL"),
        nullable=True,
    )

    session: Mapped[CoursePlanSession] = relationship(back_populates="items")
    resource: Mapped[Resource | None] = relationship(lazy="joined")
    technique: Mapped[Technique | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("position >= 0", name="course_plan_item_position"),
        CheckConstraint(
            "role IN ('core', 'extension', 'assessment')",
            name="course_plan_item_role",
        ),
        CheckConstraint(
            "resource_id IS NOT NULL OR technique_id IS NOT NULL",
            name="course_plan_item_has_link",
        ),
        Index("ix_course_plan_items_session_id", "session_id"),
        Index("ix_course_plan_items_resource_id", "resource_id"),
        Index("ix_course_plan_items_technique_id", "technique_id"),
    )
