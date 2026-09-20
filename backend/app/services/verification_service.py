"""Create, list, revoke, and redeem classroom verification tokens."""

from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.verification_token import StudentVerificationToken

_ALPHABET = string.ascii_uppercase + string.digits
# Avoid ambiguous characters in classroom codes students type by hand.
_ALPHABET = _ALPHABET.replace("O", "").replace("0", "").replace("I", "").replace("1", "").replace("L", "")


def _hash_token(plaintext: str) -> str:
    normalised = plaintext.strip().upper().replace(" ", "")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def generate_token_code() -> str:
    """Human-friendly code like `K7MP-9Q2R`."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _is_active(token: StudentVerificationToken, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if token.is_revoked:
        return False
    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= current:
        return False
    return token.max_uses is None or token.use_count < token.max_uses


def token_to_read_fields(token: StudentVerificationToken) -> dict:
    return {
        "id": token.id,
        "teacher_id": token.teacher_id,
        "label": token.label,
        "expires_at": token.expires_at,
        "max_uses": token.max_uses,
        "use_count": token.use_count,
        "is_revoked": token.is_revoked,
        "is_active": _is_active(token),
        "created_at": token.created_at,
    }


async def create_student_token(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    duration_minutes: int,
    label: str | None = None,
    max_uses: int | None = None,
) -> tuple[StudentVerificationToken, str]:
    plaintext = generate_token_code()
    row = StudentVerificationToken(
        teacher_id=teacher_id,
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


async def list_student_tokens(db: AsyncSession, teacher_id: uuid.UUID) -> list[StudentVerificationToken]:
    rows = (
        await db.scalars(
            select(StudentVerificationToken)
            .where(StudentVerificationToken.teacher_id == teacher_id)
            .order_by(StudentVerificationToken.created_at.desc())
        )
    ).all()
    return list(rows)


async def revoke_student_token(
    db: AsyncSession, *, teacher_id: uuid.UUID, token_id: uuid.UUID
) -> StudentVerificationToken:
    token = await db.scalar(
        select(StudentVerificationToken).where(
            StudentVerificationToken.id == token_id,
            StudentVerificationToken.teacher_id == teacher_id,
        )
    )
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    token.is_revoked = True
    await db.flush()
    return token


async def redeem_student_token(db: AsyncSession, *, teacher_id: uuid.UUID, plaintext: str) -> StudentVerificationToken:
    """Validate a classroom code for a teacher and consume one use."""
    token = await db.scalar(
        select(StudentVerificationToken).where(
            StudentVerificationToken.teacher_id == teacher_id,
            StudentVerificationToken.token_hash == _hash_token(plaintext),
        )
    )
    if token is None or not _is_active(token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or fully used verification token",
        )
    token.use_count += 1
    await db.flush()
    return token
