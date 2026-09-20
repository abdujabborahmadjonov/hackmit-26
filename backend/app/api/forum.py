"""Public discussion forum for educators."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.forum import ForumPost, ForumTopic
from app.schemas.common import Message as MessageEnvelope
from app.schemas.common import Page
from app.schemas.forum import (
    FORUM_CATEGORIES,
    ForumPostCreate,
    ForumPostRead,
    ForumPostUpdate,
    ForumTopicCreate,
    ForumTopicRead,
    ForumTopicUpdate,
)
from app.schemas.user import UserPublic
from app.utils.auth import CurrentUser

router = APIRouter(prefix="/forum", tags=["forum"])

DB = Annotated[AsyncSession, Depends(get_db)]


def _topic_read(topic: ForumTopic) -> ForumTopicRead:
    return ForumTopicRead(
        id=topic.id,
        author_id=topic.author_id,
        author=UserPublic.model_validate(topic.author) if topic.author else None,
        title=topic.title,
        body=topic.body,
        category=topic.category,
        reply_count=topic.reply_count,
        last_activity_at=topic.last_activity_at,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
    )


def _post_read(post: ForumPost) -> ForumPostRead:
    return ForumPostRead(
        id=post.id,
        topic_id=post.topic_id,
        author_id=post.author_id,
        author=UserPublic.model_validate(post.author) if post.author else None,
        content=post.content,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


async def _get_topic(db: AsyncSession, topic_id: uuid.UUID) -> ForumTopic:
    topic = await db.scalar(select(ForumTopic).where(ForumTopic.id == topic_id))
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


async def _get_post(db: AsyncSession, post_id: uuid.UUID) -> ForumPost:
    post = await db.scalar(select(ForumPost).where(ForumPost.id == post_id))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.get(
    "/topics",
    response_model=Page[ForumTopicRead],
    summary="Browse forum topics",
)
async def list_topics(
    current_user: CurrentUser,
    db: DB,
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    q: Annotated[str | None, Query(max_length=200, description="Search title and body")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ForumTopicRead]:
    del current_user  # auth required; listing is open to all signed-in educators
    filters = []
    if category:
        if category not in FORUM_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown category. Choose one of: {', '.join(FORUM_CATEGORIES)}",
            )
        filters.append(ForumTopic.category == category)
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(ForumTopic.title.ilike(pattern), ForumTopic.body.ilike(pattern))
        )

    count_stmt = select(func.count()).select_from(ForumTopic)
    list_stmt = select(ForumTopic).order_by(ForumTopic.last_activity_at.desc())
    if filters:
        count_stmt = count_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = await db.scalar(count_stmt) or 0
    rows = (await db.scalars(list_stmt.limit(limit).offset(offset))).unique().all()
    return Page[ForumTopicRead](
        items=[_topic_read(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/topics",
    response_model=ForumTopicRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new discussion topic",
)
async def create_topic(
    payload: ForumTopicCreate, current_user: CurrentUser, db: DB
) -> ForumTopicRead:
    topic = ForumTopic(
        author_id=current_user.id,
        title=payload.title.strip(),
        body=payload.body.strip(),
        category=payload.category,
    )
    db.add(topic)
    await db.commit()
    topic = await db.scalar(select(ForumTopic).where(ForumTopic.id == topic.id))
    assert topic is not None
    return _topic_read(topic)


@router.get(
    "/topics/{topic_id}",
    response_model=ForumTopicRead,
    summary="Get a topic",
)
async def get_topic(
    topic_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> ForumTopicRead:
    del current_user
    return _topic_read(await _get_topic(db, topic_id))


@router.put(
    "/topics/{topic_id}",
    response_model=ForumTopicRead,
    summary="Edit your topic",
)
async def update_topic(
    topic_id: uuid.UUID, payload: ForumTopicUpdate, current_user: CurrentUser, db: DB
) -> ForumTopicRead:
    topic = await _get_topic(db, topic_id)
    if topic.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own topics"
        )
    if payload.title is not None:
        topic.title = payload.title.strip()
    if payload.body is not None:
        topic.body = payload.body.strip()
    if payload.category is not None:
        topic.category = payload.category
    await db.commit()
    await db.refresh(topic)
    return _topic_read(await _get_topic(db, topic.id))


@router.delete(
    "/topics/{topic_id}",
    response_model=MessageEnvelope,
    summary="Delete your topic",
)
async def delete_topic(
    topic_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> MessageEnvelope:
    topic = await _get_topic(db, topic_id)
    if topic.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own topics"
        )
    await db.delete(topic)
    await db.commit()
    return MessageEnvelope(detail="Topic deleted")


@router.get(
    "/topics/{topic_id}/posts",
    response_model=Page[ForumPostRead],
    summary="List replies in a topic",
)
async def list_posts(
    topic_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ForumPostRead]:
    del current_user
    await _get_topic(db, topic_id)
    total = await db.scalar(
        select(func.count()).select_from(ForumPost).where(ForumPost.topic_id == topic_id)
    ) or 0
    rows = (
        await db.scalars(
            select(ForumPost)
            .where(ForumPost.topic_id == topic_id)
            .order_by(ForumPost.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
    ).unique().all()
    return Page[ForumPostRead](
        items=[_post_read(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/topics/{topic_id}/posts",
    response_model=ForumPostRead,
    status_code=status.HTTP_201_CREATED,
    summary="Reply to a topic",
)
async def create_post(
    topic_id: uuid.UUID, payload: ForumPostCreate, current_user: CurrentUser, db: DB
) -> ForumPostRead:
    await _get_topic(db, topic_id)
    post = ForumPost(
        topic_id=topic_id,
        author_id=current_user.id,
        content=payload.content.strip(),
    )
    db.add(post)
    await db.execute(
        update(ForumTopic)
        .where(ForumTopic.id == topic_id)
        .values(
            reply_count=ForumTopic.reply_count + 1,
            last_activity_at=func.now(),
            updated_at=func.now(),
        )
    )
    await db.commit()
    post = await db.scalar(select(ForumPost).where(ForumPost.id == post.id))
    assert post is not None
    return _post_read(post)


@router.put(
    "/posts/{post_id}",
    response_model=ForumPostRead,
    summary="Edit your reply",
)
async def update_post(
    post_id: uuid.UUID, payload: ForumPostUpdate, current_user: CurrentUser, db: DB
) -> ForumPostRead:
    post = await _get_post(db, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own posts"
        )
    post.content = payload.content.strip()
    await db.commit()
    post = await db.scalar(select(ForumPost).where(ForumPost.id == post.id))
    assert post is not None
    return _post_read(post)


@router.delete(
    "/posts/{post_id}",
    response_model=MessageEnvelope,
    summary="Delete your reply",
)
async def delete_post(
    post_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> MessageEnvelope:
    post = await _get_post(db, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own posts"
        )
    topic_id = post.topic_id
    await db.delete(post)
    await db.execute(
        update(ForumTopic)
        .where(ForumTopic.id == topic_id, ForumTopic.reply_count > 0)
        .values(
            reply_count=ForumTopic.reply_count - 1,
            updated_at=func.now(),
        )
    )
    await db.commit()
    return MessageEnvelope(detail="Post deleted")
