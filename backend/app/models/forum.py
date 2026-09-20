"""Public discussion forum for educators."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ForumTopic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forum_topics"

    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    reply_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    author = relationship("User", lazy="joined")
    posts: Mapped[list[ForumPost]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_forum_topics_last_activity", "last_activity_at"),
        Index("ix_forum_topics_author_id", "author_id"),
        Index("ix_forum_topics_category", "category"),
    )


class ForumPost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forum_posts"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("forum_topics.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    topic: Mapped[ForumTopic] = relationship(back_populates="posts")
    author = relationship("User", lazy="joined")

    __table_args__ = (
        Index("ix_forum_posts_topic_created", "topic_id", "created_at"),
        Index("ix_forum_posts_author_id", "author_id"),
    )
