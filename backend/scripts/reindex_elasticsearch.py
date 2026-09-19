#!/usr/bin/env python
"""Rebuild the Elasticsearch indices from Postgres (the system of record).

Writes into staging indices, refreshes, then aliases the live names over.
The previous indices stay searchable until that swap, so a failed bulk load
does not wipe production search.

    python scripts/reindex_elasticsearch.py

Production cutover: run this against the live DATABASE_URL / Elastic Cloud
credentials *before* setting SEARCH_PROVIDER=elasticsearch.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
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
        hint = (
            "Check ELASTICSEARCH_API_KEY in .env."
            if es.is_cloud_endpoint()
            else "Start it with: docker compose --profile elasticsearch up -d elasticsearch"
        )
        raise SystemExit(
            f"Elasticsearch is not reachable at {settings.elasticsearch_url}. {hint}"
        )

    token = str(time.time_ns())
    teacher_live = settings.elasticsearch_teacher_index
    resource_live = settings.elasticsearch_resource_index
    teacher_staging = es.staging_index_name(teacher_live, token)
    resource_staging = es.staging_index_name(resource_live, token)
    promoted: set[str] = set()

    try:
        await es.create_index(teacher_staging, es.TEACHER_MAPPING, replace=True)
        await es.create_index(resource_staging, es.RESOURCE_MAPPING, replace=True)

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
                    teacher_staging,
                    (
                        (str(profile.user_id), es.teacher_document(profile, user))
                        for profile, user in rows
                    ),
                    raise_on_error=True,
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
                    resource_staging,
                    ((str(resource.id), es.resource_document(resource)) for resource in rows),
                    raise_on_error=True,
                )
                resources += len(rows)
                offset += BATCH
                logger.info("Indexed %d resources", resources)

        await es.refresh_indices(teacher_staging, resource_staging)
        await es.promote_index(teacher_live, teacher_staging)
        promoted.add(teacher_staging)
        await es.promote_index(resource_live, resource_staging)
        promoted.add(resource_staging)
    except Exception:
        for staging in (teacher_staging, resource_staging):
            if staging not in promoted:
                try:
                    await es.delete_index(staging)
                except Exception as cleanup_exc:  # pragma: no cover - best-effort
                    logger.warning("Could not drop unused staging index %s: %s", staging, cleanup_exc)
        raise

    await es.close_client()
    logger.info("Done: %d teachers, %d resources", teachers, resources)
    return teachers, resources


async def main() -> int:
    await reindex_all()
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
