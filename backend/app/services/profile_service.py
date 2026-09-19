"""Profile write-path helpers: embedding refresh, rating rollups, index sync."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.user import User
from app.services import elasticsearch_service as es
from app.services.embedding_service import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


def profile_embedding_text(profile: TeacherProfile) -> str:
    """The exact text we embed for a teacher (teaching style + bio + expertise)."""
    return EmbeddingService.build_profile_text(
        teaching_style=profile.teaching_style,
        bio=profile.bio,
        fields_of_expertise=profile.fields_of_expertise,
        subjects=profile.subjects,
        teaching_methods=profile.teaching_methods,
        education_levels=profile.education_levels,
    )


async def refresh_profile_embedding(
    profile: TeacherProfile, embeddings: EmbeddingService | None = None
) -> bool:
    """Regenerate the teaching-style vector. Called only on profile writes."""
    embeddings = embeddings or get_embedding_service()
    text = profile_embedding_text(profile)
    if not text:
        profile.teaching_style_embedding = None
        return False
    profile.teaching_style_embedding = await embeddings.generate_embedding(text)
    return True


async def sync_profile_to_index(db: AsyncSession, profile: TeacherProfile) -> None:
    """Mirror the profile into Elasticsearch (no-op for the Postgres engine)."""
    user = await db.scalar(select(User).where(User.id == profile.user_id))
    if user is not None:
        await es.index_teacher(profile, user)


async def recalculate_teacher_rating(db: AsyncSession, teacher_id: uuid.UUID) -> tuple[float, int]:
    """Recompute average_rating / rating_count from the ratings table."""
    row = (
        await db.execute(
            select(func.coalesce(func.avg(Rating.rating), 0.0), func.count(Rating.id)).where(
                Rating.teacher_id == teacher_id
            )
        )
    ).one()
    average, count = float(row[0] or 0.0), int(row[1] or 0)
    await db.execute(
        update(TeacherProfile)
        .where(TeacherProfile.user_id == teacher_id)
        .values(average_rating=round(average, 2), rating_count=count)
    )
    return round(average, 2), count
