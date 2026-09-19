"""Registration, login and the current-user endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.common import Message
from app.schemas.user import UserPrivate
from app.utils.auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.utils.rate_limit import AuthRateLimit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

DB = Annotated[AsyncSession, Depends(get_db)]


def _token_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, email=user.email),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description=(
        "Registers an educator and returns a JWT access token. Passwords are "
        "hashed with Argon2id and are never stored or returned in plaintext."
    ),
)
async def register(payload: RegisterRequest, db: DB, _: AuthRateLimit = None) -> TokenResponse:
    email = payload.email.lower().strip()
    existing = await db.scalar(select(User.id).where(func.lower(User.email) == email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        profile_photo_url=payload.profile_photo_url,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        ) from None
    await db.refresh(user)
    logger.info("Registered user %s", user.id)
    return _token_for(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Exchange email + password for a JWT",
)
async def login(payload: LoginRequest, db: DB, _: AuthRateLimit = None) -> TokenResponse:
    email = payload.email.lower().strip()
    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    # Same error for "no such user" and "wrong password" - no account enumeration.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        await db.commit()
    return _token_for(user)


@router.get(
    "/me",
    response_model=UserPrivate,
    summary="The authenticated account",
)
async def me(current_user: CurrentUser) -> UserPrivate:
    return UserPrivate.model_validate(current_user)


@router.post(
    "/change-password",
    response_model=Message,
    summary="Change the account password",
)
async def change_password(
    payload: PasswordChangeRequest, current_user: CurrentUser, db: DB
) -> Message:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    current_user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return Message(detail="Password updated")
