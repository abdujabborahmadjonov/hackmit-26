"""Teacher profile: the structured + semantic representation we match on."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Float,
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

from app.config import settings
from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User


class TeacherProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    bio: Mapped[str | None] = mapped_column(Text)

    # Approximate/public location only - we never store street addresses.
    location_name: Mapped[str | None] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    # What they teach
    education_levels: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )
    subjects: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )
    fields_of_expertise: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    # How they teach
    teaching_levels: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )
    teaching_methods: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )
    teaching_style: Mapped[str | None] = mapped_column(Text)
    class_size: Mapped[int | None] = mapped_column(Integer)
    years_experience: Mapped[int | None] = mapped_column(Integer)

    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    institution: Mapped[str | None] = mapped_column(String(200))
    institution_type: Mapped[str | None] = mapped_column(String(50))

    average_rating: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )
    rating_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # Semantic fingerprint of bio + teaching style + expertise + methods.
    teaching_style_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim)
    )

    # Personal recommendation factor weights (overrides bandit when set).
    recommendation_weights: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped[User] = relationship(back_populates="profile")

    __table_args__ = (
        CheckConstraint("class_size IS NULL OR class_size > 0", name="class_size_positive"),
        CheckConstraint(
            "years_experience IS NULL OR years_experience >= 0", name="experience_non_negative"
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="latitude_range"
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="longitude_range",
        ),
        Index("ix_teacher_profiles_subjects", "subjects", postgresql_using="gin"),
        Index("ix_teacher_profiles_expertise", "fields_of_expertise", postgresql_using="gin"),
        Index("ix_teacher_profiles_education_levels", "education_levels", postgresql_using="gin"),
        Index("ix_teacher_profiles_teaching_levels", "teaching_levels", postgresql_using="gin"),
        Index("ix_teacher_profiles_teaching_methods", "teaching_methods", postgresql_using="gin"),
        Index("ix_teacher_profiles_average_rating", "average_rating"),
        Index("ix_teacher_profiles_class_size", "class_size"),
        Index("ix_teacher_profiles_location", "latitude", "longitude"),
        # Approximate nearest neighbour index for the candidate-retrieval step.
        Index(
            "ix_teacher_profiles_embedding_hnsw",
            "teaching_style_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"teaching_style_embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TeacherProfile user_id={self.user_id}>"
