"""Connection requests: the professional-network layer."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.connection import Connection, ConnectionStatus
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.connection import ConnectionCreate, ConnectionRead, ConnectionUpdate
from app.utils.auth import CurrentUser

router = APIRouter(prefix="/connections", tags=["connections"])

DB = Annotated[AsyncSession, Depends(get_db)]


async def _find_between(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> Connection | None:
    """Existing connection in either direction."""
    return await db.scalar(
        select(Connection).where(
            or_(
                (Connection.requester_id == a) & (Connection.receiver_id == b),
                (Connection.requester_id == b) & (Connection.receiver_id == a),
            )
        )
    )


@router.post(
    "",
    response_model=ConnectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a connection request",
    description=(
        "Duplicate requests are rejected in either direction. If the other "
        "educator already invited you, accept their request instead."
    ),
)
async def create_connection(
    payload: ConnectionCreate, current_user: CurrentUser, db: DB
) -> ConnectionRead:
    if payload.receiver_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot connect with yourself"
        )
    receiver = await db.scalar(
        select(User).where(User.id == payload.receiver_id, User.is_active.is_(True))
    )
    if receiver is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Educator not found")

    existing = await _find_between(db, current_user.id, payload.receiver_id)
    if existing is not None:
        if existing.status == ConnectionStatus.BLOCKED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="This connection is blocked"
            )
        if existing.status == ConnectionStatus.REJECTED and existing.receiver_id == current_user.id:
            # They turned you down before; let the other side re-open it.
            existing.status = ConnectionStatus.PENDING
            existing.requester_id, existing.receiver_id = current_user.id, payload.receiver_id
            await db.commit()
            await db.refresh(existing)
            return ConnectionRead.model_validate(existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A connection already exists with status '{existing.status.value}'",
        )

    connection = Connection(
        requester_id=current_user.id,
        receiver_id=payload.receiver_id,
        status=ConnectionStatus.PENDING,
    )
    db.add(connection)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A connection already exists"
        ) from None
    await db.refresh(connection)
    return ConnectionRead.model_validate(connection)


@router.get(
    "",
    response_model=Page[ConnectionRead],
    summary="Your connections",
)
async def list_connections(
    current_user: CurrentUser,
    db: DB,
    connection_status: Annotated[
        ConnectionStatus | None, Query(alias="status", description="Filter by status")
    ] = None,
    direction: Annotated[
        str, Query(pattern="^(all|incoming|outgoing)$")
    ] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ConnectionRead]:
    filters = []
    if direction == "incoming":
        filters.append(Connection.receiver_id == current_user.id)
    elif direction == "outgoing":
        filters.append(Connection.requester_id == current_user.id)
    else:
        filters.append(
            or_(
                Connection.requester_id == current_user.id,
                Connection.receiver_id == current_user.id,
            )
        )
    if connection_status is not None:
        filters.append(Connection.status == connection_status)

    total = await db.scalar(select(func.count()).select_from(Connection).where(*filters)) or 0
    rows = (
        await db.scalars(
            select(Connection)
            .where(*filters)
            .order_by(Connection.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).unique().all()
    return Page[ConnectionRead](
        items=[ConnectionRead.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.put(
    "/{connection_id}",
    response_model=ConnectionRead,
    summary="Accept, reject or block a connection",
    description="Only the receiver can accept or reject. Either side can block.",
)
async def update_connection(
    connection_id: uuid.UUID, payload: ConnectionUpdate, current_user: CurrentUser, db: DB
) -> ConnectionRead:
    connection = await db.scalar(select(Connection).where(Connection.id == connection_id))
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    if current_user.id not in (connection.requester_id, connection.receiver_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This connection is not yours"
        )

    new_status = payload.status
    if new_status == ConnectionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot move a connection back to pending"
        )
    if new_status in (ConnectionStatus.ACCEPTED, ConnectionStatus.REJECTED):
        if connection.receiver_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the recipient can accept or reject a request",
            )
        if connection.status != ConnectionStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Request is already '{connection.status.value}'",
            )

    connection.status = new_status
    await db.commit()
    await db.refresh(connection)
    return ConnectionRead.model_validate(connection)


@router.delete(
    "/{connection_id}",
    response_model=Message,
    summary="Remove a connection or withdraw a request",
)
async def delete_connection(
    connection_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> Message:
    connection = await db.scalar(select(Connection).where(Connection.id == connection_id))
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    if current_user.id not in (connection.requester_id, connection.receiver_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This connection is not yours"
        )
    await db.delete(connection)
    await db.commit()
    return Message(detail="Connection removed")
