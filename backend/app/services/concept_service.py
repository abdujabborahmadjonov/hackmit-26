"""Concept vocabulary: embed, merge, and canonicalize candidate phrases."""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import Concept, ConceptAlias
from app.services.embedding_service import cosine_similarity, get_embedding_service
from app.services import llm_service

logger = logging.getLogger(__name__)

# Tunable merge thresholds (approved defaults).
MERGE_THRESHOLD = 0.92
CREATE_THRESHOLD = 0.75

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalise_alias(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def slugify(text: str, *, subject: str | None = None) -> str:
    base = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    if subject:
        prefix = _SLUG_RE.sub("_", subject.strip().lower()).strip("_")
        if prefix and not base.startswith(prefix):
            base = f"{prefix}_{base}"
    return base[:120] or "concept"


async def embed_texts(texts: list[str]) -> list[list[float]]:
    service = get_embedding_service()
    return await service.generate_embeddings(texts)


async def find_by_alias(db: AsyncSession, text: str) -> Concept | None:
    norm = normalise_alias(text)
    alias = await db.scalar(
        select(ConceptAlias).where(ConceptAlias.alias_norm == norm)
    )
    if alias is None:
        return None
    return await db.scalar(select(Concept).where(Concept.id == alias.concept_id))


async def nearest_concepts(
    db: AsyncSession,
    vector: list[float],
    *,
    subject: str | None = None,
    limit: int = 5,
) -> list[tuple[Concept, float]]:
    """Return concepts ranked by cosine similarity to `vector`."""
    query = select(Concept).where(Concept.embedding.is_not(None))
    if subject:
        query = query.where(Concept.subject == subject)
    rows = (await db.scalars(query.limit(500))).all()
    scored: list[tuple[Concept, float]] = []
    for concept in rows:
        if concept.embedding is None:
            continue
        score = cosine_similarity(vector, list(concept.embedding))
        scored.append((concept, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


async def create_concept(
    db: AsyncSession,
    *,
    label: str,
    subject: str,
    description: str | None = None,
    embedding: list[float] | None = None,
) -> Concept:
    slug = slugify(label, subject=subject)
    # Ensure unique slug.
    existing = await db.scalar(select(Concept).where(Concept.slug == slug))
    if existing is not None:
        slug = f"{slug}_{uuid.uuid4().hex[:6]}"

    if embedding is None:
        embedding = (await embed_texts([label]))[0]

    concept = Concept(
        slug=slug,
        label=label.strip(),
        subject=subject.strip().lower().replace(" ", "_"),
        description=description,
        embedding=embedding,
    )
    db.add(concept)
    await db.flush()
    db.add(
        ConceptAlias(
            concept_id=concept.id,
            alias=label.strip(),
            alias_norm=normalise_alias(label),
        )
    )
    await db.flush()
    return concept


async def add_alias(db: AsyncSession, concept: Concept, alias: str) -> ConceptAlias | None:
    norm = normalise_alias(alias)
    existing = await db.scalar(
        select(ConceptAlias).where(ConceptAlias.alias_norm == norm)
    )
    if existing is not None:
        return None
    row = ConceptAlias(concept_id=concept.id, alias=alias.strip(), alias_norm=norm)
    db.add(row)
    await db.flush()
    return row


async def canonicalize(
    db: AsyncSession,
    *,
    label: str,
    subject: str,
    description: str | None = None,
    use_llm_borderline: bool = True,
) -> Concept:
    """Merge into vocabulary or create a new concept."""
    existing = await find_by_alias(db, label)
    if existing is not None:
        return existing

    vector = (await embed_texts([label]))[0]
    neighbours = await nearest_concepts(db, vector, subject=subject, limit=3)
    best: Concept | None = None
    best_score = 0.0
    if neighbours:
        best, best_score = neighbours[0]

    if best is not None and best_score >= MERGE_THRESHOLD:
        await add_alias(db, best, label)
        return best

    if best is None or best_score <= CREATE_THRESHOLD:
        return await create_concept(
            db, label=label, subject=subject, description=description, embedding=vector
        )

    # Borderline: ask the LLM when available.
    if use_llm_borderline and llm_service.is_enabled():
        try:
            decision = await llm_service.decide_concept_merge(
                candidate=label,
                nearest_label=best.label,
                nearest_description=best.description,
                similarity=best_score,
            )
            if decision == "merge":
                await add_alias(db, best, label)
                return best
        except llm_service.LLMUnavailable:
            logger.info("LLM unavailable for concept merge; creating new concept")

    return await create_concept(
        db, label=label, subject=subject, description=description, embedding=vector
    )


async def extract_and_canonicalize_from_text(
    db: AsyncSession,
    *,
    text: str,
    subject: str,
    pdf: bytes | None = None,
) -> list[Concept]:
    """LLM concept extraction then canonicalize each phrase."""
    labels = await llm_service.extract_concepts_from_document(text=text, pdf=pdf)
    concepts: list[Concept] = []
    seen: set[uuid.UUID] = set()
    for label in labels:
        concept = await canonicalize(db, label=label, subject=subject)
        if concept.id not in seen:
            seen.add(concept.id)
            concepts.append(concept)
    return concepts
