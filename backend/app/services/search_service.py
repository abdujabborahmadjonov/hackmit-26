"""Teacher + resource search.

Two interchangeable engines behind one interface (SEARCH_PROVIDER):

* `postgres`      - SQL filters, pg_trgm/tsvector lexical ranking and pgvector
                    cosine similarity. No extra infrastructure.
* `elasticsearch` - BM25 + kNN + geo_distance in a single query, for when the
                    corpus outgrows a single Postgres box.

Both return the same objects: Postgres remains the system of record, so the
Elasticsearch path resolves hits back to ORM rows before serialisation.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Float, Select, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.profile import TeacherProfile
from app.models.resource import Resource
from app.models.user import User
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.taxonomy import canonical_term, slugify
from app.utils.geo import bounding_box, haversine_km

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0088


# --------------------------------------------------------------------------- #
# Query objects
# --------------------------------------------------------------------------- #
@dataclass
class TeacherSearchQuery:
    query: str | None = None
    subject: str | None = None
    education_level: str | None = None
    teaching_level: str | None = None
    teaching_method: str | None = None
    teaching_style: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    minimum_rating: float | None = None
    class_size: int | None = None
    class_size_tolerance: float = 0.4
    language: str | None = None
    institution_type: str | None = None
    min_years_experience: int | None = None
    sort: str = "relevance"  # relevance | rating | experience | distance | newest
    limit: int = 20
    offset: int = 0
    exclude_user_id: uuid.UUID | None = None

    @property
    def has_geo(self) -> bool:
        return self.latitude is not None and self.longitude is not None and self.radius_km


@dataclass
class ResourceSearchQuery:
    query: str | None = None
    subject: str | None = None
    education_level: str | None = None
    difficulty: str | None = None
    teaching_method: str | None = None
    resource_type: str | None = None
    tags: list[str] = field(default_factory=list)
    owner_id: uuid.UUID | None = None
    sort: str = "relevance"
    limit: int = 20
    offset: int = 0


@dataclass
class TeacherHit:
    profile: TeacherProfile
    user: User
    score: float
    distance_km: float | None = None
    highlights: list[str] = field(default_factory=list)


@dataclass
class SearchOutcome:
    hits: list
    total: int
    engine: str
    took_ms: float


def _haversine_expr(lat: float, lon: float):
    """Great-circle distance in km as a SQL expression (for filter + sort)."""
    lat_col = cast(TeacherProfile.latitude, Float)
    lon_col = cast(TeacherProfile.longitude, Float)
    return (
        2
        * EARTH_RADIUS_KM
        * func.asin(
            func.sqrt(
                func.power(func.sin(func.radians(lat_col - lat) / 2), 2)
                + func.cos(func.radians(lat))
                * func.cos(func.radians(lat_col))
                * func.power(func.sin(func.radians(lon_col - lon) / 2), 2)
            )
        )
    )


# --------------------------------------------------------------------------- #
# Postgres engine
# --------------------------------------------------------------------------- #
class PostgresSearchBackend:
    name = "postgres"

    def __init__(self, db: AsyncSession, embeddings: EmbeddingService) -> None:
        self.db = db
        self.embeddings = embeddings

    # --- teachers ---------------------------------------------------------- #
    def _teacher_filters(self, q: TeacherSearchQuery) -> list:
        filters = [User.is_active.is_(True)]
        if q.exclude_user_id:
            filters.append(TeacherProfile.user_id != q.exclude_user_id)
        if q.subject:
            term = canonical_term(q.subject)
            filters.append(
                or_(
                    TeacherProfile.subjects.any(term),
                    TeacherProfile.fields_of_expertise.any(term),
                )
            )
        if q.education_level:
            filters.append(TeacherProfile.education_levels.any(slugify(q.education_level)))
        if q.teaching_level:
            filters.append(TeacherProfile.teaching_levels.any(slugify(q.teaching_level)))
        if q.teaching_method:
            filters.append(TeacherProfile.teaching_methods.any(slugify(q.teaching_method)))
        if q.teaching_style:
            # Free-text style filter: match the method vocabulary or the prose.
            style_slug = slugify(q.teaching_style)
            filters.append(
                or_(
                    TeacherProfile.teaching_methods.any(style_slug),
                    TeacherProfile.teaching_style.ilike(f"%{q.teaching_style}%"),
                )
            )
        if q.location and not q.has_geo:
            filters.append(TeacherProfile.location_name.ilike(f"%{q.location}%"))
        if q.minimum_rating is not None:
            filters.append(TeacherProfile.average_rating >= q.minimum_rating)
        if q.class_size:
            delta = max(1, int(q.class_size * q.class_size_tolerance))
            filters.append(
                and_(
                    TeacherProfile.class_size.is_not(None),
                    TeacherProfile.class_size.between(q.class_size - delta, q.class_size + delta),
                )
            )
        if q.language:
            filters.append(TeacherProfile.languages.any(q.language))
        if q.institution_type:
            filters.append(TeacherProfile.institution_type == slugify(q.institution_type))
        if q.min_years_experience is not None:
            filters.append(TeacherProfile.years_experience >= q.min_years_experience)
        if q.has_geo:
            min_lat, max_lat, min_lon, max_lon = bounding_box(
                q.latitude, q.longitude, q.radius_km  # type: ignore[arg-type]
            )
            filters.extend(
                [
                    TeacherProfile.latitude.between(min_lat, max_lat),
                    TeacherProfile.longitude.between(min_lon, max_lon),
                    _haversine_expr(q.latitude, q.longitude) <= q.radius_km,  # type: ignore[arg-type]
                ]
            )
        return filters

    async def search_teachers(self, q: TeacherSearchQuery) -> SearchOutcome:
        started = time.perf_counter()
        filters = self._teacher_filters(q)

        total = await self.db.scalar(
            select(func.count())
            .select_from(TeacherProfile)
            .join(User, User.id == TeacherProfile.user_id)
            .where(*filters)
        ) or 0

        stmt: Select = (
            select(TeacherProfile, User)
            .join(User, User.id == TeacherProfile.user_id)
            .where(*filters)
        )

        score_expr = None
        if q.query:
            embedding = await self.embeddings.generate_embedding(q.query)
            semantic = 1 - TeacherProfile.teaching_style_embedding.cosine_distance(embedding)
            document = func.to_tsvector(
                "english",
                func.concat_ws(
                    " ",
                    func.coalesce(TeacherProfile.bio, ""),
                    func.coalesce(TeacherProfile.teaching_style, ""),
                    func.coalesce(TeacherProfile.institution, ""),
                    func.coalesce(TeacherProfile.location_name, ""),
                ),
            )
            tsquery = func.websearch_to_tsquery("english", q.query)
            # normalisation flag 32 keeps ts_rank_cd inside [0, 1)
            lexical = func.ts_rank_cd(document, tsquery, 32)
            score_expr = (
                0.7 * func.coalesce(semantic, 0.0) + 0.3 * func.coalesce(lexical, 0.0)
            ).label("score")
            stmt = stmt.add_columns(score_expr)

        distance_expr = None
        if q.has_geo:
            distance_expr = _haversine_expr(q.latitude, q.longitude).label("distance_km")
            stmt = stmt.add_columns(distance_expr)

        stmt = self._apply_sort(stmt, q, score_expr, distance_expr)
        rows = (await self.db.execute(stmt.limit(q.limit).offset(q.offset))).all()

        hits: list[TeacherHit] = []
        for row in rows:
            profile, user = row[0], row[1]
            score = 1.0
            distance = None
            index = 2
            if score_expr is not None:
                score = max(0.0, min(1.0, float(row[index] or 0.0)))
                index += 1
            if distance_expr is not None:
                distance = float(row[index]) if row[index] is not None else None
            elif q.latitude is not None and q.longitude is not None and profile.latitude is not None:
                distance = haversine_km(q.latitude, q.longitude, profile.latitude, profile.longitude)
            hits.append(TeacherHit(profile=profile, user=user, score=score, distance_km=distance))

        return SearchOutcome(
            hits=hits,
            total=int(total),
            engine=self.name,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def _apply_sort(stmt: Select, q: TeacherSearchQuery, score_expr, distance_expr) -> Select:
        if q.sort == "rating":
            return stmt.order_by(
                TeacherProfile.average_rating.desc(), TeacherProfile.rating_count.desc()
            )
        if q.sort == "experience":
            return stmt.order_by(TeacherProfile.years_experience.desc().nullslast())
        if q.sort == "newest":
            return stmt.order_by(TeacherProfile.created_at.desc())
        if q.sort == "distance" and distance_expr is not None:
            return stmt.order_by(distance_expr.asc())
        if score_expr is not None:
            return stmt.order_by(score_expr.desc(), TeacherProfile.average_rating.desc())
        if distance_expr is not None:
            return stmt.order_by(distance_expr.asc())
        return stmt.order_by(
            TeacherProfile.average_rating.desc(), TeacherProfile.rating_count.desc()
        )

    # --- resources --------------------------------------------------------- #
    async def search_resources(self, q: ResourceSearchQuery) -> SearchOutcome:
        started = time.perf_counter()
        filters = []
        if q.subject:
            filters.append(Resource.subject == canonical_term(q.subject))
        if q.education_level:
            filters.append(Resource.education_level == slugify(q.education_level))
        if q.difficulty:
            filters.append(Resource.difficulty == slugify(q.difficulty))
        if q.teaching_method:
            filters.append(Resource.teaching_method == slugify(q.teaching_method))
        if q.resource_type:
            filters.append(Resource.resource_type == slugify(q.resource_type))
        if q.tags:
            filters.append(Resource.tags.overlap([canonical_term(t) for t in q.tags]))
        if q.owner_id:
            filters.append(Resource.owner_id == q.owner_id)

        total = await self.db.scalar(
            select(func.count()).select_from(Resource).where(*filters)
        ) or 0

        stmt: Select = select(Resource).where(*filters)
        score_expr = None
        if q.query:
            embedding = await self.embeddings.generate_embedding(q.query)
            semantic = 1 - Resource.embedding.cosine_distance(embedding)
            document = func.to_tsvector(
                "english",
                func.concat_ws(
                    " ", func.coalesce(Resource.title, ""), func.coalesce(Resource.description, "")
                ),
            )
            lexical = func.ts_rank_cd(document, func.websearch_to_tsquery("english", q.query), 32)
            score_expr = (
                0.7 * func.coalesce(semantic, 0.0) + 0.3 * func.coalesce(lexical, 0.0)
            ).label("score")
            stmt = stmt.add_columns(score_expr).order_by(score_expr.desc())
        elif q.sort == "newest" or q.sort == "relevance":
            stmt = stmt.order_by(Resource.created_at.desc())
        elif q.sort == "popular":
            stmt = stmt.order_by(Resource.download_count.desc())

        rows = (await self.db.execute(stmt.limit(q.limit).offset(q.offset))).all()
        hits = [
            (row[0], max(0.0, min(1.0, float(row[1]))) if score_expr is not None else 1.0)
            for row in rows
        ]
        return SearchOutcome(
            hits=hits,
            total=int(total),
            engine=self.name,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )


# --------------------------------------------------------------------------- #
# Elasticsearch engine
# --------------------------------------------------------------------------- #
class ElasticsearchSearchBackend:
    name = "elasticsearch"

    def __init__(self, db: AsyncSession, embeddings: EmbeddingService) -> None:
        self.db = db
        self.embeddings = embeddings

    @staticmethod
    def _teacher_filters(q: TeacherSearchQuery) -> list[dict]:
        filters: list[dict] = []
        if q.subject:
            term = canonical_term(q.subject)
            filters.append(
                {
                    "bool": {
                        "should": [
                            {"term": {"subjects": term}},
                            {"term": {"fields_of_expertise": term}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        if q.education_level:
            filters.append({"term": {"education_levels": slugify(q.education_level)}})
        if q.teaching_level:
            filters.append({"term": {"teaching_levels": slugify(q.teaching_level)}})
        if q.teaching_method:
            filters.append({"term": {"teaching_methods": slugify(q.teaching_method)}})
        if q.teaching_style:
            filters.append(
                {
                    "bool": {
                        "should": [
                            {"term": {"teaching_methods": slugify(q.teaching_style)}},
                            {"match": {"teaching_style": q.teaching_style}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        if q.location and not q.has_geo:
            filters.append({"match": {"location_name": q.location}})
        if q.minimum_rating is not None:
            filters.append({"range": {"average_rating": {"gte": q.minimum_rating}}})
        if q.class_size:
            delta = max(1, int(q.class_size * q.class_size_tolerance))
            filters.append(
                {
                    "range": {
                        "class_size": {"gte": q.class_size - delta, "lte": q.class_size + delta}
                    }
                }
            )
        if q.language:
            filters.append({"term": {"languages": q.language}})
        if q.institution_type:
            filters.append({"term": {"institution_type": slugify(q.institution_type)}})
        if q.min_years_experience is not None:
            filters.append({"range": {"years_experience": {"gte": q.min_years_experience}}})
        if q.has_geo:
            filters.append(
                {
                    "geo_distance": {
                        "distance": f"{q.radius_km}km",
                        "location": {"lat": q.latitude, "lon": q.longitude},
                    }
                }
            )
        return filters

    @staticmethod
    def _sort_clause(q: TeacherSearchQuery) -> list | None:
        if q.sort == "rating":
            return [{"average_rating": "desc"}, {"rating_count": "desc"}]
        if q.sort == "experience":
            return [{"years_experience": "desc"}]
        if q.sort == "newest":
            return [{"updated_at": "desc"}]
        if q.sort == "distance" and q.has_geo:
            return [
                {
                    "_geo_distance": {
                        "location": {"lat": q.latitude, "lon": q.longitude},
                        "order": "asc",
                        "unit": "km",
                    }
                }
            ]
        return None

    async def search_teachers(self, q: TeacherSearchQuery) -> SearchOutcome:
        from app.services import elasticsearch_service as es

        started = time.perf_counter()
        client = es.get_client()
        filters = self._teacher_filters(q)
        must_not = (
            [{"term": {"user_id": str(q.exclude_user_id)}}] if q.exclude_user_id else []
        )

        body: dict = {
            "query": {
                "bool": {
                    "filter": filters,
                    "must_not": must_not,
                    "should": [],
                }
            },
            "from": q.offset,
            "size": q.limit,
            "track_total_hits": True,
            "_source": ["user_id"],
        }

        if q.query:
            body["query"]["bool"]["should"] = [
                {
                    "multi_match": {
                        "query": q.query,
                        "fields": [
                            "teaching_style^3",
                            "bio^2",
                            "full_name^2",
                            "institution",
                            "location_name",
                        ],
                        "fuzziness": "AUTO",
                    }
                }
            ]
            # Hybrid: BM25 above, kNN below. Elasticsearch merges both rankings.
            embedding = await self.embeddings.generate_embedding(q.query)
            body["knn"] = {
                "field": "embedding",
                "query_vector": embedding,
                "k": max(q.limit + q.offset, 50),
                "num_candidates": max((q.limit + q.offset) * 10, 200),
                "boost": 2.0,
                **({"filter": filters} if filters else {}),
            }

        sort = self._sort_clause(q)
        if sort:
            body["sort"] = sort

        response = await client.search(index=settings.elasticsearch_teacher_index, body=body)
        hits_raw = response["hits"]["hits"]
        total = response["hits"]["total"]["value"]
        max_score = max((hit.get("_score") or 0.0) for hit in hits_raw) if hits_raw else 1.0
        max_score = max_score or 1.0

        ordered_ids = [uuid.UUID(hit["_source"]["user_id"]) for hit in hits_raw]
        scores = {
            uuid.UUID(hit["_source"]["user_id"]): (hit.get("_score") or 0.0) / max_score
            for hit in hits_raw
        }
        rows = (
            await self.db.execute(
                select(TeacherProfile, User)
                .join(User, User.id == TeacherProfile.user_id)
                .where(TeacherProfile.user_id.in_(ordered_ids))
            )
        ).all()
        by_id = {profile.user_id: (profile, user) for profile, user in rows}

        hits: list[TeacherHit] = []
        for user_id in ordered_ids:
            found = by_id.get(user_id)
            if not found:  # index drifted from the database
                continue
            profile, user = found
            distance = None
            if q.latitude is not None and q.longitude is not None and profile.latitude is not None:
                distance = haversine_km(
                    q.latitude, q.longitude, profile.latitude, profile.longitude
                )
            hits.append(
                TeacherHit(
                    profile=profile,
                    user=user,
                    score=max(0.0, min(1.0, scores.get(user_id, 1.0))),
                    distance_km=distance,
                )
            )

        if ordered_ids and not hits:
            logger.warning(
                "Elasticsearch returned %d teacher hits but none exist in Postgres. "
                "Reindex with: python scripts/reindex_elasticsearch.py",
                len(ordered_ids),
            )

        return SearchOutcome(
            hits=hits,
            total=int(total),
            engine=self.name,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def search_resources(self, q: ResourceSearchQuery) -> SearchOutcome:
        from app.services import elasticsearch_service as es

        started = time.perf_counter()
        client = es.get_client()
        filters: list[dict] = []
        if q.subject:
            filters.append({"term": {"subject": canonical_term(q.subject)}})
        if q.education_level:
            filters.append({"term": {"education_level": slugify(q.education_level)}})
        if q.difficulty:
            filters.append({"term": {"difficulty": slugify(q.difficulty)}})
        if q.teaching_method:
            filters.append({"term": {"teaching_method": slugify(q.teaching_method)}})
        if q.resource_type:
            filters.append({"term": {"resource_type": slugify(q.resource_type)}})
        if q.tags:
            filters.append({"terms": {"tags": [canonical_term(t) for t in q.tags]}})
        if q.owner_id:
            filters.append({"term": {"owner_id": str(q.owner_id)}})

        body: dict = {
            "query": {"bool": {"filter": filters}},
            "from": q.offset,
            "size": q.limit,
            "track_total_hits": True,
            "_source": ["resource_id"],
        }
        if q.query:
            body["query"]["bool"]["should"] = [
                {
                    "multi_match": {
                        "query": q.query,
                        "fields": ["title^3", "description", "tags^2"],
                        "fuzziness": "AUTO",
                    }
                }
            ]
            embedding = await self.embeddings.generate_embedding(q.query)
            body["knn"] = {
                "field": "embedding",
                "query_vector": embedding,
                "k": max(q.limit + q.offset, 50),
                "num_candidates": max((q.limit + q.offset) * 10, 200),
                "boost": 2.0,
                **({"filter": filters} if filters else {}),
            }
        elif q.sort in ("newest", "relevance"):
            body["sort"] = [{"created_at": "desc"}]

        response = await client.search(index=settings.elasticsearch_resource_index, body=body)
        hits_raw = response["hits"]["hits"]
        total = response["hits"]["total"]["value"]
        max_score = max((hit.get("_score") or 0.0) for hit in hits_raw) if hits_raw else 1.0
        max_score = max_score or 1.0

        ordered_ids = [uuid.UUID(hit["_source"]["resource_id"]) for hit in hits_raw]
        scores = {
            uuid.UUID(hit["_source"]["resource_id"]): (hit.get("_score") or 0.0) / max_score
            for hit in hits_raw
        }
        resources = {
            resource.id: resource
            for resource in (
                await self.db.scalars(select(Resource).where(Resource.id.in_(ordered_ids)))
            ).all()
        }
        hits = [
            (resources[rid], max(0.0, min(1.0, scores.get(rid, 1.0))))
            for rid in ordered_ids
            if rid in resources
        ]
        if ordered_ids and not hits:
            logger.warning(
                "Elasticsearch returned %d resource hits but none exist in Postgres. "
                "Reindex with: python scripts/reindex_elasticsearch.py",
                len(ordered_ids),
            )
        return SearchOutcome(
            hits=hits,
            total=int(total),
            engine=self.name,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #
class SearchService:
    """Picks the configured engine and degrades gracefully to Postgres."""

    def __init__(self, db: AsyncSession, embeddings: EmbeddingService | None = None) -> None:
        self.db = db
        self.embeddings = embeddings or get_embedding_service()
        self.postgres = PostgresSearchBackend(db, self.embeddings)
        self.elastic = (
            ElasticsearchSearchBackend(db, self.embeddings)
            if settings.search_provider == "elasticsearch"
            else None
        )

    async def search_teachers(self, q: TeacherSearchQuery) -> SearchOutcome:
        if self.elastic is not None:
            try:
                outcome = await self.elastic.search_teachers(q)
                if outcome.hits or outcome.total == 0:
                    return outcome
                # Stale index after a DB rebuild: ES knows about documents whose
                # IDs no longer exist in Postgres, so the page would look empty.
                logger.warning(
                    "Elasticsearch teacher search returned total=%d but 0 resolvable hits; using Postgres",
                    outcome.total,
                )
                return await self.postgres.search_teachers(q)
            except Exception as exc:
                if not settings.search_fallback_to_postgres:
                    raise
                logger.warning("Elasticsearch teacher search failed (%s); using Postgres", exc)
        return await self.postgres.search_teachers(q)

    async def search_resources(self, q: ResourceSearchQuery) -> SearchOutcome:
        if self.elastic is not None:
            try:
                outcome = await self.elastic.search_resources(q)
                if outcome.hits or outcome.total == 0:
                    return outcome
                logger.warning(
                    "Elasticsearch resource search returned total=%d but 0 resolvable hits; using Postgres",
                    outcome.total,
                )
                return await self.postgres.search_resources(q)
            except Exception as exc:
                if not settings.search_fallback_to_postgres:
                    raise
                logger.warning("Elasticsearch resource search failed (%s); using Postgres", exc)
        return await self.postgres.search_resources(q)
