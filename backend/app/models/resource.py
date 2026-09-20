"""Educational resources shared by teachers."""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Resource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resources"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(String(1000))
    file_name: Mapped[str | None] = mapped_column(String(300))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(120))

    resource_type: Mapped[str | None] = mapped_column(String(50))
    subject: Mapped[str | None] = mapped_column(String(80))
    education_level: Mapped[str | None] = mapped_column(String(50))
    difficulty: Mapped[str | None] = mapped_column(String(30))
    teaching_method: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    download_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))

    owner = relationship("User", lazy="joined")

    __table_args__ = (
        Index("ix_resources_owner_id", "owner_id"),
        Index("ix_resources_subject", "subject"),
        Index("ix_resources_education_level", "education_level"),
        Index("ix_resources_difficulty", "difficulty"),
        Index("ix_resources_teaching_method", "teaching_method"),
        Index("ix_resources_tags", "tags", postgresql_using="gin"),
        Index("ix_resources_created_at", "created_at"),
        Index(
            "ix_resources_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Resource {self.title!r}>"
