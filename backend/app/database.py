"""Async SQLAlchemy engine/session wiring plus pgvector bootstrapping."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import DateTime, MetaData, event, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

logger = logging.getLogger(__name__)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def _ensure_vector_type(engine: AsyncEngine) -> None:
    """Make sure the `vector` type exists on every new asyncpg connection.

    We deliberately do NOT register pgvector's asyncpg binary codec here:
    pgvector's SQLAlchemy type already serialises vectors to their text form,
    and registering the codec as well would double-encode them. Instead we just
    guarantee the extension is present so a brand new database self-heals.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        async def setup(conn):  # pragma: no cover - exercised via integration tests
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        try:
            dbapi_connection.run_async(setup)
        except Exception as exc:  # pragma: no cover - e.g. a read-only replica
            logger.debug("Could not ensure the pgvector extension: %s", exc)


def connect_args_for(url: str) -> dict:
    """Driver arguments that depend on what is on the other end of the socket."""
    args: dict = {}
    if "+asyncpg" in url and settings.db_disable_prepared_statements:
        # Both caches must go: the dialect's own LRU and asyncpg's.
        args["prepared_statement_cache_size"] = 0
        args["statement_cache_size"] = 0
    return args


def create_engine(url: str | None = None, **kwargs) -> AsyncEngine:
    url = url or settings.database_url
    engine = create_async_engine(
        url,
        echo=kwargs.pop("echo", settings.db_echo),
        pool_size=kwargs.pop("pool_size", settings.db_pool_size),
        max_overflow=kwargs.pop("max_overflow", settings.db_max_overflow),
        pool_pre_ping=True,
        connect_args=kwargs.pop("connect_args", connect_args_for(url)),
        **kwargs,
    )
    _ensure_vector_type(engine)
    return engine


engine: AsyncEngine = create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def ensure_extensions(target_engine: AsyncEngine | None = None) -> None:
    """Create the extensions the schema depends on (idempotent)."""
    target = target_engine or engine
    async with target.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))
    logger.info("pgvector and pg_trgm extensions are ready")
