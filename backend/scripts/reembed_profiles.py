#!/usr/bin/env python3
"""Re-embed teacher profiles, techniques, and concepts with the active provider.

Use after switching EMBEDDING_PROVIDER (e.g. hashing → voyage) so ANN indexes
are not mixing incompatible vector spaces.

    python scripts/reembed_profiles.py
    python scripts/reembed_profiles.py --batch-size 64 --only profiles
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models.concept import Concept
from app.models.profile import TeacherProfile
from app.models.technique import Technique
from app.services.embedding_service import get_embedding_service
from app.services.profile_service import profile_embedding_text
from app.services.technique_search_service import technique_embedding_text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reembed")


async def _embed_batch(texts: list[str]) -> list[list[float]]:
    service = get_embedding_service()
    return await service.generate_embeddings(texts)


async def reembed_profiles(batch_size: int) -> int:
    updated = 0
    async with SessionLocal() as db:
        total = await db.scalar(select(func.count()).select_from(TeacherProfile)) or 0
        offset = 0
        while offset < total:
            rows = list(
                (
                    await db.scalars(
                        select(TeacherProfile).order_by(TeacherProfile.id).offset(offset).limit(batch_size)
                    )
                ).all()
            )
            if not rows:
                break
            texts = [profile_embedding_text(p) for p in rows]
            vectors = await _embed_batch(texts)
            for profile, vector in zip(rows, vectors, strict=True):
                profile.teaching_style_embedding = vector
            await db.commit()
            updated += len(rows)
            offset += batch_size
            logger.info("profiles %d / %d", updated, total)
    return updated


async def reembed_techniques(batch_size: int) -> int:
    updated = 0
    async with SessionLocal() as db:
        total = await db.scalar(select(func.count()).select_from(Technique)) or 0
        offset = 0
        while offset < total:
            rows = list(
                (
                    await db.scalars(
                        select(Technique).order_by(Technique.id).offset(offset).limit(batch_size)
                    )
                ).all()
            )
            if not rows:
                break
            texts = [technique_embedding_text(t) for t in rows]
            vectors = await _embed_batch(texts)
            for tech, vector in zip(rows, vectors, strict=True):
                tech.embedding = vector
            await db.commit()
            updated += len(rows)
            offset += batch_size
            logger.info("techniques %d / %d", updated, total)
    return updated


async def reembed_concepts(batch_size: int) -> int:
    updated = 0
    async with SessionLocal() as db:
        total = await db.scalar(select(func.count()).select_from(Concept)) or 0
        offset = 0
        while offset < total:
            rows = list(
                (
                    await db.scalars(
                        select(Concept).order_by(Concept.id).offset(offset).limit(batch_size)
                    )
                ).all()
            )
            if not rows:
                break
            texts = [
                " ".join(part for part in [c.label, c.subject, c.description or ""] if part)
                for c in rows
            ]
            vectors = await _embed_batch(texts)
            for concept, vector in zip(rows, vectors, strict=True):
                concept.embedding = vector
            await db.commit()
            updated += len(rows)
            offset += batch_size
            logger.info("concepts %d / %d", updated, total)
    return updated


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--only",
        choices=("profiles", "techniques", "concepts", "all"),
        default="all",
    )
    args = parser.parse_args()

    logger.info(
        "Re-embedding with provider=%s dim=%s model=%s",
        settings.embedding_provider,
        settings.embedding_dim,
        settings.embedding_model or "(default)",
    )
    if args.only in ("profiles", "all"):
        await reembed_profiles(args.batch_size)
    if args.only in ("techniques", "all"):
        await reembed_techniques(args.batch_size)
    if args.only in ("concepts", "all"):
        await reembed_concepts(args.batch_size)


if __name__ == "__main__":
    asyncio.run(main())
