"""Canonical teaching concepts and aliases for vocabulary merge."""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Concept(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "concepts"

    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Stretch: optional parent for prerequisite graphs.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="SET NULL"),
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))

    aliases: Mapped[list[ConceptAlias]] = relationship(
        back_populates="concept", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_concepts_subject", "subject"),
        Index("ix_concepts_label", "label"),
        Index(
            "ix_concepts_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Concept {self.slug!r}>"


class ConceptAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "concept_aliases"

    concept_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    alias_norm: Mapped[str] = mapped_column(String(200), nullable=False)

    concept: Mapped[Concept] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("alias_norm", name="uq_concept_aliases_alias_norm"),
        Index("ix_concept_aliases_concept_id", "concept_id"),
        Index("ix_concept_aliases_alias_norm", "alias_norm"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConceptAlias {self.alias!r}>"
