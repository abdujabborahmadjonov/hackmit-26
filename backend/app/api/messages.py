"""Direct messaging between educators.

Security note: messages travel over HTTPS and are stored server-side so they
can be delivered and searched. EduMatch does NOT implement end-to-end
encryption, and the API never claims that it does.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.user import User
from app.schemas.common import Message as MessageEnvelope, Page
from app.schemas.message import (
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
)
from app.schemas.user import UserPublic
from app.utils.auth import CurrentUser

router = APIRouter(prefix="/messages", tags=["messages"])

DB = Annotated[AsyncSession, Depends(get_db)]


async def _assert_participant(
    db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    member = await db.scalar(
        select(ConversationParticipant.user_id).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation",
        )


async def _existing_conversation(
    db: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> uuid.UUID | None:
    """The 1:1 conversation shared by two users, if there is one."""
    mine = select(ConversationParticipant.conversation_id).where(
        ConversationParticipant.user_id == a
    )
    return await db.scalar(
        select(ConversationParticipant.conversation_id)
        .where(
            ConversationParticipant.user_id == b,
            ConversationParticipant.conversation_id.in_(mine),
        )
        .limit(1)
    )


async def _build_conversation_read(
    db: AsyncSession, conversation: Conversation, viewer_id: uuid.UUID
) -> ConversationRead:
    participants = [
        UserPublic.model_validate(participant.user) for participant in conversation.participants
    ]
    last_message = await db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    unread = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.sender_id != viewer_id,
            Message.read_at.is_(None),
        )
    )
    return ConversationRead(
        id=conversation.id,
        participants=participants,
        last_message=MessageRead.model_validate(last_message) if last_message else None,
        unread_count=int(unread or 0),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start (or reopen) a conversation",
    description="Returns the existing 1:1 conversation if one already exists.",
)
async def create_conversation(
    payload: ConversationCreate, current_user: CurrentUser, db: DB
) -> ConversationRead:
    if payload.participant_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot start a conversation with yourself",
        )
    other = await db.scalar(
        select(User).where(User.id == payload.participant_id, User.is_active.is_(True))
    )
    if other is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Educator not found")

    conversation_id = await _existing_conversation(db, current_user.id, payload.participant_id)
    if conversation_id is None:
        conversation = Conversation()
        db.add(conversation)
        await db.flush()
        db.add_all(
            [
                ConversationParticipant(conversation_id=conversation.id, user_id=current_user.id),
                ConversationParticipant(
                    conversation_id=conversation.id, user_id=payload.participant_id
                ),
            ]
        )
        conversation_id = conversation.id

    if payload.content:
        db.add(
            Message(
                conversation_id=conversation_id,
                sender_id=current_user.id,
                content=payload.content,
            )
        )
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )
    await db.commit()

    conversation = await db.scalar(select(Conversation).where(Conversation.id == conversation_id))
    return await _build_conversation_read(db, conversation, current_user.id)


@router.get(
    "/conversations",
    response_model=Page[ConversationRead],
    summary="Your conversations, most recent first",
)
async def list_conversations(
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ConversationRead]:
    mine = select(ConversationParticipant.conversation_id).where(
        ConversationParticipant.user_id == current_user.id
    )
    total = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.id.in_(mine))
    ) or 0
    conversations = (
        await db.scalars(
            select(Conversation)
            .where(Conversation.id.in_(mine))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).unique().all()
    items = [
        await _build_conversation_read(db, conversation, current_user.id)
        for conversation in conversations
    ]
    return Page[ConversationRead](items=items, total=int(total), limit=limit, offset=offset)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=Page[MessageRead],
    summary="Messages in a conversation",
)
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MessageRead]:
    await _assert_participant(db, conversation_id, current_user.id)
    total = await db.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
    ) or 0
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).unique().all()
    return Page[MessageRead](
        items=[MessageRead.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
)
async def send_message(
    conversation_id: uuid.UUID, payload: MessageCreate, current_user: CurrentUser, db: DB
) -> MessageRead:
    await _assert_participant(db, conversation_id, current_user.id)
    message = Message(
        conversation_id=conversation_id, sender_id=current_user.id, content=payload.content
    )
    db.add(message)
    await db.execute(
        update(Conversation).where(Conversation.id == conversation_id).values(updated_at=func.now())
    )
    await db.commit()
    await db.refresh(message)
    return MessageRead.model_validate(message)


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=MessageEnvelope,
    summary="Mark everything in a conversation as read",
)
async def mark_read(
    conversation_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> MessageEnvelope:
    await _assert_participant(db, conversation_id, current_user.id)
    result = await db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_id != current_user.id,
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return MessageEnvelope(detail=f"Marked {result.rowcount} message(s) as read")
