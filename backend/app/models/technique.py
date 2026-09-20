"""Teaching techniques, concept links, student ratings, and shareable rating links."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.class_profile import ClassProfile
    from app.models.concept import Concept
    from app.models.user import User

PROBLEM_TYPES = (
    "misconception",
    "missing_prerequisite",
    "engagement",
    "pacing",
    "transfer",
)


class Technique(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "techniques"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(250), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[str] = mapped_column(Text, nullable=False)
    materials: Mapped[str | None] = mapped_column(Text)
    class_time_minutes: Mapped[int | None] = mapped_column(Integer)
    teaching_style: Mapped[str | None] = mapped_column(String(80))

    # Context the technique was developed / used in.
    context_subject: Mapped[str | None] = mapped_column(String(80))
    context_level: Mapped[str | None] = mapped_column(String(50))
    context_format: Mapped[str | None] = mapped_column(String(20))
    context_class_size: Mapped[int | None] = mapped_column(Integer)
    context_notes: Mapped[str | None] = mapped_column(Text)

    problem_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    average_rating: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )
    rating_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))

    owner: Mapped[User] = relationship(lazy="joined")
    concepts: Mapped[list[TechniqueConcept]] = relationship(
        back_populates="technique", cascade="all, delete-orphan", lazy="selectin"
    )
    ratings: Mapped[list[TechniqueRating]] = relationship(
        back_populates="technique", cascade="all, delete-orphan", lazy="noload"
    )

    __table_args__ = (
        CheckConstraint(
            "class_time_minutes IS NULL OR class_time_minutes > 0",
            name="technique_time_positive",
        ),
        CheckConstraint(
            "context_class_size IS NULL OR context_class_size > 0",
            name="technique_context_size_positive",
        ),
        Index("ix_techniques_owner_id", "owner_id"),
        Index("ix_techniques_context_subject", "context_subject"),
        Index("ix_techniques_problem_types", "problem_types", postgresql_using="gin"),
        Index("ix_techniques_average_rating", "average_rating"),
        Index("ix_techniques_is_published", "is_published"),
        Index(
            "ix_techniques_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Technique {self.title!r}>"


class TechniqueConcept(Base):
    __tablename__ = "technique_concepts"

    technique_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("techniques.id", ondelete="CASCADE"),
        nullable=False,
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
    )

    technique: Mapped[Technique] = relationship(back_populates="concepts")
    concept: Mapped[Concept] = relationship(lazy="joined")

    __table_args__ = (
        PrimaryKeyConstraint("technique_id", "concept_id", name="pk_technique_concepts"),
        Index("ix_technique_concepts_concept_id", "concept_id"),
    )


class TechniqueRating(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Anonymous student rating of a technique; no PII."""

    __tablename__ = "technique_ratings"

    technique_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("techniques.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Class context of the teacher who ran the technique (for similarity weighting).
    class_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("class_profiles.id", ondelete="SET NULL"),
    )
    rating_link_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("rating_links.id", ondelete="SET NULL"),
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    # Snapshot of rater class context so similarity still works if profile changes.
    context_subject: Mapped[str | None] = mapped_column(String(80))
    context_level: Mapped[str | None] = mapped_column(String(50))
    context_format: Mapped[str | None] = mapped_column(String(20))
    context_class_size: Mapped[int | None] = mapped_column(Integer)

    technique: Mapped[Technique] = relationship(back_populates="ratings")
    class_profile: Mapped[ClassProfile | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="technique_rating_range"),
        Index("ix_technique_ratings_technique_id", "technique_id"),
        Index("ix_technique_ratings_class_profile_id", "class_profile_id"),
    )


class RatingLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use (or limited-use) token for anonymous technique ratings."""

    __tablename__ = "rating_links"

    technique_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("techniques.id", ondelete="CASCADE"),
        nullable=False,
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    class_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("class_profiles.id", ondelete="SET NULL"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    technique: Mapped[Technique] = relationship(lazy="joined")
    class_profile: Mapped[ClassProfile | None] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_rating_links_technique_id", "technique_id"),
        Index("ix_rating_links_teacher_id", "teacher_id"),
        Index("ix_rating_links_expires_at", "expires_at"),
    )
