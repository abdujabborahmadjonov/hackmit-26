#!/usr/bin/env python
"""Rebuild the Elasticsearch indices from Postgres (the system of record).

    SEARCH_PROVIDER=elasticsearch python scripts/reindex_elasticsearch.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.models.profile import TeacherProfile  # noqa: E402
from app.models.resource import Resource  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import elasticsearch_service as es  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("reindex")

BATCH = 500


async def reindex_all() -> tuple[int, int]:
    if settings.search_provider != "elasticsearch":
        logger.warning(
            "SEARCH_PROVIDER=%s - indexing anyway so you can switch engines later",
            settings.search_provider,
        )
    if not await es.ping():
        raise SystemExit(
            f"Elasticsearch is not reachable at {settings.elasticsearch_url}. "
            "Start it with: docker compose --profile elasticsearch up -d elasticsearch"
        )

    await es.ensure_indices()

    teachers = resources = 0
    async with SessionLocal() as session:
        offset = 0
        while True:
            rows = (
                await session.execute(
                    select(TeacherProfile, User)
                    .join(User, User.id == TeacherProfile.user_id)
                    .order_by(TeacherProfile.created_at)
                    .limit(BATCH)
                    .offset(offset)
                )
            ).all()
            if not rows:
                break
            await es.bulk_index(
                settings.elasticsearch_teacher_index,
                ((str(profile.user_id), es.teacher_document(profile, user)) for profile, user in rows),
            )
            teachers += len(rows)
            offset += BATCH
            logger.info("Indexed %d teachers", teachers)

        offset = 0
        while True:
            rows = (
                await session.scalars(
                    select(Resource).order_by(Resource.created_at).limit(BATCH).offset(offset)
                )
            ).all()
            if not rows:
                break
            await es.bulk_index(
                settings.elasticsearch_resource_index,
                ((str(resource.id), es.resource_document(resource)) for resource in rows),
            )
            resources += len(rows)
            offset += BATCH
            logger.info("Indexed %d resources", resources)

    await es.refresh_indices()
    await es.close_client()
    logger.info("Done: %d teachers, %d resources", teachers, resources)
    return teachers, resources


async def main() -> int:
    await reindex_all()
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
