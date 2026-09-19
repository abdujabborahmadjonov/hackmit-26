#!/usr/bin/env python
"""Measure recommendation latency on whatever dataset is currently loaded.

    python scripts/benchmark_recommendations.py --runs 25
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.models.profile import TeacherProfile  # noqa: E402
from app.models.resource import Resource  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.recommendation_service import RecommendationService  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark GET /recommendations")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--pool", type=int, default=None, help="Candidate pool override")
    args = parser.parse_args()

    async with SessionLocal() as session:
        teachers = await session.scalar(select(func.count()).select_from(TeacherProfile))
        resources = await session.scalar(select(func.count()).select_from(Resource))
        sample = (
            await session.scalars(
                select(User.id)
                .join(TeacherProfile, TeacherProfile.user_id == User.id)
                .limit(args.runs)
            )
        ).all()
        if not sample:
            print("No teacher profiles found - run scripts/generate_demo_data.py first.")
            return 1

        service = RecommendationService(session)
        # Warm the connection and the index pages.
        await service.recommend(sample[0], limit=args.limit, pool_size=args.pool, log_events=False)

        timings: list[float] = []
        pool_sizes: list[int] = []
        for user_id in sample:
            started = time.perf_counter()
            result = await service.recommend(
                user_id, limit=args.limit, pool_size=args.pool, log_events=False
            )
            timings.append((time.perf_counter() - started) * 1000)
            pool_sizes.append(result.candidate_pool_size)

    timings.sort()
    print(f"\nDataset      : {teachers:,} teacher profiles, {resources:,} resources")
    print(f"Runs         : {len(timings)} (limit={args.limit})")
    print(f"Candidates   : {statistics.mean(pool_sizes):.0f} scored per request (mean)")
    print(f"Mean         : {statistics.mean(timings):.1f} ms")
    print(f"Median       : {statistics.median(timings):.1f} ms")
    print(f"p95          : {timings[int(len(timings) * 0.95) - 1]:.1f} ms")
    print(f"Max          : {timings[-1]:.1f} ms\n")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
