#!/usr/bin/env python
"""Offline eval for the teacher recommendation ranker (synthetic relevance).

Relevance rule (tunable):
  - share at least one subject/expertise term (after canonicalisation), AND
  - education compatibility >= edu_min, AND
  - (optional) semantic cosine >= semantic_min when both have embeddings

Metrics: Precision@k, nDCG@k, MRR. Ablations: with/without MMR.

    python scripts/eval_recommendations.py --viewers 20 --k 10
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.profile import TeacherProfile  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.embedding_service import cosine_similarity  # noqa: E402
from app.services.recommendation_service import (  # noqa: E402
    RecommendationService,
    education_similarity,
)
from app.taxonomy import canonical_terms  # noqa: E402


def is_relevant(
    viewer: TeacherProfile,
    candidate: TeacherProfile,
    *,
    edu_min: float,
    semantic_min: float,
) -> bool:
    viewer_terms = canonical_terms(
        list(viewer.subjects or []) + list(viewer.fields_of_expertise or [])
    )
    cand_terms = canonical_terms(
        list(candidate.subjects or []) + list(candidate.fields_of_expertise or [])
    )
    if not (viewer_terms & cand_terms):
        return False
    if education_similarity(viewer.education_levels, candidate.education_levels) < edu_min:
        return False
    if (
        viewer.teaching_style_embedding is not None
        and candidate.teaching_style_embedding is not None
        and semantic_min > 0
    ):
        sim = cosine_similarity(
            list(viewer.teaching_style_embedding), list(candidate.teaching_style_embedding)
        )
        if sim < semantic_min:
            return False
    return True


def precision_at_k(relevances: list[bool], k: int) -> float:
    top = relevances[:k]
    if not top:
        return 0.0
    return sum(1 for r in top if r) / len(top)


def dcg(relevances: list[bool], k: int) -> float:
    score = 0.0
    for i, rel in enumerate(relevances[:k]):
        if rel:
            score += 1.0 / math.log2(i + 2)
    return score


def ndcg_at_k(relevances: list[bool], k: int) -> float:
    ideal = sorted(relevances, reverse=True)
    denom = dcg(ideal, k)
    if denom <= 0:
        return 0.0
    return dcg(relevances, k) / denom


def mrr(relevances: list[bool]) -> float:
    for i, rel in enumerate(relevances):
        if rel:
            return 1.0 / (i + 1)
    return 0.0


async def evaluate(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        ids = list(
            (
                await session.scalars(
                    select(User.id)
                    .join(TeacherProfile, TeacherProfile.user_id == User.id)
                    .order_by(func.random())
                    .limit(args.viewers)
                )
            ).all()
        )
        if not ids:
            print("No teacher profiles found. Generate demo data first.")
            return 1

        service = RecommendationService(session)
        metrics = {"p": [], "ndcg": [], "mrr": [], "p_nommr": [], "ndcg_nommr": []}

        for user_id in ids:
            viewer = await session.scalar(
                select(TeacherProfile).where(TeacherProfile.user_id == user_id)
            )
            assert viewer is not None

            with_mmr = await service.recommend(
                user_id, limit=args.k, pool_size=args.pool, log_events=False, mmr=True
            )
            without = await service.recommend(
                user_id, limit=args.k, pool_size=args.pool, log_events=False, mmr=False
            )

            def labels(result, viewer_profile=viewer):
                return [
                    is_relevant(
                        viewer_profile,
                        item.profile,
                        edu_min=args.edu_min,
                        semantic_min=args.semantic_min,
                    )
                    for item in result.items
                ]

            rel_mmr = labels(with_mmr)
            rel_plain = labels(without)
            metrics["p"].append(precision_at_k(rel_mmr, args.k))
            metrics["ndcg"].append(ndcg_at_k(rel_mmr, args.k))
            metrics["mrr"].append(mrr(rel_mmr))
            metrics["p_nommr"].append(precision_at_k(rel_plain, args.k))
            metrics["ndcg_nommr"].append(ndcg_at_k(rel_plain, args.k))

        def avg(key: str) -> float:
            vals = metrics[key]
            return sum(vals) / len(vals) if vals else 0.0

        print(f"viewers={len(ids)} k={args.k} pool={args.pool}")
        print(f"Precision@{args.k} (MMR)     {avg('p'):.4f}")
        print(f"nDCG@{args.k} (MMR)          {avg('ndcg'):.4f}")
        print(f"MRR (MMR)                   {avg('mrr'):.4f}")
        print(f"Precision@{args.k} (no MMR)  {avg('p_nommr'):.4f}")
        print(f"nDCG@{args.k} (no MMR)       {avg('ndcg_nommr'):.4f}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewers", type=int, default=25)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--pool", type=int, default=200)
    parser.add_argument("--edu-min", type=float, default=0.3)
    parser.add_argument("--semantic-min", type=float, default=0.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(evaluate(args)))


if __name__ == "__main__":
    main()
