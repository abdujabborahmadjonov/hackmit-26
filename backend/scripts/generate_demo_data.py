#!/usr/bin/env python
"""Generate a realistic EduMatch dataset.

Examples
--------
    # Full dataset (10k users, 50k resources, 30k ratings, 20k connections)
    python scripts/generate_demo_data.py

    # Fast dataset for a laptop demo (~10% of the above, ~15 seconds)
    python scripts/generate_demo_data.py --scale 0.1

    # Keep existing data and add 500 more teachers
    python scripts/generate_demo_data.py --users 500 --resources 0 --no-truncate
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import SessionLocal, engine, ensure_extensions  # noqa: E402
from app.services.demo_data_service import (  # noqa: E402
    DEMO_PASSWORD,
    DemoDataGenerator,
    GenerationCounts,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("demo-data")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic EduMatch data")
    parser.add_argument("--users", type=int, default=10_000)
    parser.add_argument("--resources", type=int, default=50_000)
    parser.add_argument("--ratings", type=int, default=30_000)
    parser.add_argument("--connections", type=int, default=20_000)
    parser.add_argument("--conversations", type=int, default=500)
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Multiply every count (e.g. 0.1 for a quick demo dataset)",
    )
    parser.add_argument("--seed", type=int, default=2026, help="Deterministic output")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--no-truncate",
        dest="truncate",
        action="store_false",
        help="Append to the existing data instead of wiping it first",
    )
    parser.add_argument(
        "--keep-indexes",
        dest="rebuild_indexes",
        action="store_false",
        help="Do not drop/rebuild the pgvector HNSW indexes around the bulk load",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Push everything into Elasticsearch afterwards (SEARCH_PROVIDER=elasticsearch)",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    counts = GenerationCounts(
        users=max(int(args.users * args.scale), 4),
        resources=int(args.resources * args.scale),
        ratings=int(args.ratings * args.scale),
        connections=int(args.connections * args.scale),
        conversations=int(args.conversations * args.scale),
    )

    logger.info("Database: %s", settings.database_url.split("@")[-1])
    logger.info(
        "Target: %d users, %d resources, %d ratings, %d connections",
        counts.users,
        counts.resources,
        counts.ratings,
        counts.connections,
    )

    await ensure_extensions()
    async with SessionLocal() as session:
        generator = DemoDataGenerator(
            session, counts, seed=args.seed, batch_size=args.batch_size
        )
        stats = await generator.run(
            truncate=args.truncate, rebuild_indexes=args.rebuild_indexes
        )

    print("\n" + "=" * 62)
    print("  EduMatch demo data ready")
    print("=" * 62)
    print(f"  users          : {stats.users:,}")
    print(f"  teacher profiles: {stats.profiles:,}")
    print(f"  resources      : {stats.resources:,}")
    print(f"  ratings        : {stats.ratings:,}")
    print(f"  connections    : {stats.connections:,}")
    print(f"  conversations  : {stats.conversations:,} ({stats.messages:,} messages)")
    print(f"  elapsed        : {stats.seconds}s")
    print("-" * 62)
    print("  Demo logins (password for every account below):")
    print(f"      {DEMO_PASSWORD}")
    for email in stats.demo_accounts:
        print(f"      {email}")
    print("=" * 62 + "\n")

    if args.reindex:
        from scripts.reindex_elasticsearch import reindex_all

        await reindex_all()

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
