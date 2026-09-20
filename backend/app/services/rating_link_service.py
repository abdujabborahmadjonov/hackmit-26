"""Single-use rating links for anonymous technique ratings."""

from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.technique import RatingLink

_ALPHABET = string.ascii_lowercase + string.digits


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.strip().encode("utf-8")).hexdigest()


def generate_rating_token() -> str:
    """URL-safe token (not a classroom typing code)."""
    return secrets.token_urlsafe(18)


def is_active(link: RatingLink, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if link.is_revoked:
        return False
    expires = link.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= current:
        return False
    return link.max_uses is None or link.use_count < link.max_uses


def link_to_read_fields(link: RatingLink, *, token: str | None = None) -> dict:
    return {
        "id": link.id,
        "technique_id": link.technique_id,
        "teacher_id": link.teacher_id,
        "class_profile_id": link.class_profile_id,
        "label": link.label,
        "expires_at": link.expires_at,
        "max_uses": link.max_uses,
        "use_count": link.use_count,
        "is_revoked": link.is_revoked,
        "is_active": is_active(link),
        "created_at": link.created_at,
        "token": token,
        "rate_path": f"/rate/{token}" if token else None,
    }


async def create_rating_link(
    db: AsyncSession,
    *,
    technique_id: uuid.UUID,
    teacher_id: uuid.UUID,
    class_profile_id: uuid.UUID | None,
    duration_minutes: int,
    label: str | None = None,
    max_uses: int | None = None,
) -> tuple[RatingLink, str]:
    plaintext = generate_rating_token()
    row = RatingLink(
        technique_id=technique_id,
        teacher_id=teacher_id,
        class_profile_id=class_profile_id,
        token_hash=_hash_token(plaintext),
        label=label,
        expires_at=datetime.now(UTC) + timedelta(minutes=duration_minutes),
        max_uses=max_uses,
        use_count=0,
        is_revoked=False,
    )
    db.add(row)
    await db.flush()
    return row, plaintext


async def get_active_link_by_token(db: AsyncSession, plaintext: str) -> RatingLink:
    link = await db.scalar(
        select(RatingLink).where(RatingLink.token_hash == _hash_token(plaintext))
    )
    if link is None or not is_active(link):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or fully used rating link",
        )
    return link


async def consume_link(db: AsyncSession, link: RatingLink) -> RatingLink:
    if not is_active(link):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or fully used rating link",
        )
    link.use_count += 1
    await db.flush()
    return link


async def revoke_link(
    db: AsyncSession, *, teacher_id: uuid.UUID, link_id: uuid.UUID
) -> RatingLink:
    link = await db.scalar(
        select(RatingLink).where(
            RatingLink.id == link_id,
            RatingLink.teacher_id == teacher_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    link.is_revoked = True
    await db.flush()
    return link
