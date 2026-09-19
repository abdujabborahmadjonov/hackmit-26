"""Recommendation telemetry.

Every served recommendation is logged with its component scores. That gives us
(a) an audit trail for "why this match?", and (b) a place to record user
feedback so the weights can be tuned later.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RecommendationFeedback(str, enum.Enum):
    NONE = "none"
    SAVED = "saved"
    DISMISSED = "dismissed"
    CONNECTED = "connected"


class RecommendationEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recommended_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    feedback: Mapped[RecommendationFeedback] = mapped_column(
        Enum(
            RecommendationFeedback,
            name="recommendation_feedback",
            values_callable=lambda e: [i.value for i in e],
        ),
        nullable=False,
        default=RecommendationFeedback.NONE,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "recommended_user_id", name="uq_recommendation_pair"),
        Index("ix_recommendation_events_user_id", "user_id"),
    )
