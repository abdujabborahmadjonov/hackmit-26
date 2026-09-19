"""Elasticsearch engine: index management, document sync and hybrid queries.

Enabled with SEARCH_PROVIDER=elasticsearch. Postgres stays the system of
record; Elasticsearch is a derived index that gives us BM25 relevance,
geo_distance filtering and kNN vector search in a single query.

Auth: Elastic Cloud uses ELASTICSEARCH_API_KEY; self-hosted clusters can use
ELASTICSEARCH_USERNAME / ELASTICSEARCH_PASSWORD. The API key wins if both are set.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

TEACHER_MAPPING: dict[str, Any] = {
    "properties": {
        "user_id": {"type": "keyword"},
        "first_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "last_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "full_name": {"type": "text"},
        "bio": {"type": "text", "analyzer": "english"},
        "teaching_style": {"type": "text", "analyzer": "english"},
        "location_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "location": {"type": "geo_point"},
        "education_levels": {"type": "keyword"},
        "subjects": {"type": "keyword"},
        "fields_of_expertise": {"type": "keyword"},
        "teaching_levels": {"type": "keyword"},
        "teaching_methods": {"type": "keyword"},
        "languages": {"type": "keyword"},
        "institution": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "institution_type": {"type": "keyword"},
        "class_size": {"type": "integer"},
        "years_experience": {"type": "integer"},
        "average_rating": {"type": "float"},
        "rating_count": {"type": "integer"},
        "updated_at": {"type": "date"},
        "embedding": {
            "type": "dense_vector",
            "dims": settings.embedding_dim,
            "index": True,
            "similarity": "cosine",
        },
    }
}

RESOURCE_MAPPING: dict[str, Any] = {
    "properties": {
        "resource_id": {"type": "keyword"},
        "owner_id": {"type": "keyword"},
        "title": {"type": "text", "analyzer": "english"},
        "description": {"type": "text", "analyzer": "english"},
        "resource_type": {"type": "keyword"},
        "subject": {"type": "keyword"},
        "education_level": {"type": "keyword"},
        "difficulty": {"type": "keyword"},
        "teaching_method": {"type": "keyword"},
        "tags": {"type": "keyword"},
        "created_at": {"type": "date"},
        "embedding": {
            "type": "dense_vector",
            "dims": settings.embedding_dim,
            "index": True,
            "similarity": "cosine",
        },
    }
}


class ElasticsearchUnavailable(RuntimeError):
    """Raised when the cluster cannot be reached or the client is missing."""


_client: Any = None

_ELASTIC_CLOUD_HOST_MARKER = ".es."
_ELASTIC_CLOUD_DOMAIN = "elastic.cloud"


def is_cloud_endpoint(url: str | None = None) -> bool:
    """True for Elastic Cloud / HTTPS-managed clusters (API key + cluster-managed replicas)."""
    host = (url or settings.elasticsearch_url).lower()
    return _ELASTIC_CLOUD_DOMAIN in host or _ELASTIC_CLOUD_HOST_MARKER in host


def client_kwargs() -> dict[str, Any]:
    """Auth and transport options. API keys win over basic auth (Elastic Cloud)."""
    kwargs: dict[str, Any] = {
        "request_timeout": 15,
        "retry_on_timeout": True,
        "max_retries": 2,
    }
    api_key = settings.elasticsearch_api_key.strip()
    username = settings.elasticsearch_username.strip()
    if api_key:
        kwargs["api_key"] = api_key
    elif username:
        kwargs["basic_auth"] = (username, settings.elasticsearch_password)
    return kwargs


def index_create_settings() -> dict[str, Any] | None:
    """Shard/replica hints. Cloud and serverless manage these; local single-node needs 0 replicas."""
    if is_cloud_endpoint():
        return None
    return {"number_of_shards": 1, "number_of_replicas": 0}


def get_client() -> Any:
    """Lazily build a shared AsyncElasticsearch client."""
    global _client
    if _client is not None:
        return _client
    try:
        from elasticsearch import AsyncElasticsearch
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise ElasticsearchUnavailable(
            "The 'elasticsearch' package is not installed but SEARCH_PROVIDER=elasticsearch"
        ) from exc

    _client = AsyncElasticsearch(settings.elasticsearch_url, **client_kwargs())
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ping() -> bool:
    try:
        return bool(await get_client().ping())
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Elasticsearch ping failed: %s", exc)
        return False


async def ensure_indices() -> None:
    """Create both indices with their mappings if they do not exist yet."""
    client = get_client()
    create_settings = index_create_settings()
    for index, mapping in (
        (settings.elasticsearch_teacher_index, TEACHER_MAPPING),
        (settings.elasticsearch_resource_index, RESOURCE_MAPPING),
    ):
        if await client.indices.exists(index=index):
            continue
        create_kwargs: dict[str, Any] = {"index": index, "mappings": mapping}
        if create_settings is not None:
            create_kwargs["settings"] = create_settings
        try:
            await client.indices.create(**create_kwargs)
        except Exception as exc:
            # Elastic Cloud Serverless rejects shard/replica settings. Retry bare.
            if create_settings is None or await client.indices.exists(index=index):
                raise
            logger.warning(
                "Creating %s with explicit shard settings failed (%s); retrying without them",
                index,
                exc,
            )
            await client.indices.create(index=index, mappings=mapping)
        logger.info("Created Elasticsearch index %s", index)


async def recreate_indices() -> None:
    """Drop and recreate both indices so a reindex cannot mix in stale IDs."""
    client = get_client()
    for index in (
        settings.elasticsearch_teacher_index,
        settings.elasticsearch_resource_index,
    ):
        await client.indices.delete(index=index, ignore_unavailable=True)
        logger.info("Dropped Elasticsearch index %s", index)
    await ensure_indices()


# --------------------------------------------------------------------------- #
# Document builders
# --------------------------------------------------------------------------- #
def teacher_document(profile, user) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "user_id": str(profile.user_id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": f"{user.first_name} {user.last_name}",
        "bio": profile.bio,
        "teaching_style": profile.teaching_style,
        "location_name": profile.location_name,
        "education_levels": list(profile.education_levels or []),
        "subjects": list(profile.subjects or []),
        "fields_of_expertise": list(profile.fields_of_expertise or []),
        "teaching_levels": list(profile.teaching_levels or []),
        "teaching_methods": list(profile.teaching_methods or []),
        "languages": list(profile.languages or []),
        "institution": profile.institution,
        "institution_type": profile.institution_type,
        "class_size": profile.class_size,
        "years_experience": profile.years_experience,
        "average_rating": profile.average_rating,
        "rating_count": profile.rating_count,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
    if profile.latitude is not None and profile.longitude is not None:
        doc["location"] = {"lat": profile.latitude, "lon": profile.longitude}
    if profile.teaching_style_embedding is not None:
        doc["embedding"] = list(profile.teaching_style_embedding)
    return doc


def resource_document(resource) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "resource_id": str(resource.id),
        "owner_id": str(resource.owner_id),
        "title": resource.title,
        "description": resource.description,
        "resource_type": resource.resource_type,
        "subject": resource.subject,
        "education_level": resource.education_level,
        "difficulty": resource.difficulty,
        "teaching_method": resource.teaching_method,
        "tags": list(resource.tags or []),
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
    }
    if resource.embedding is not None:
        doc["embedding"] = list(resource.embedding)
    return doc


# --------------------------------------------------------------------------- #
# Sync helpers (safe to call even when Elasticsearch is not the active engine)
# --------------------------------------------------------------------------- #
async def index_teacher(profile, user) -> None:
    if settings.search_provider != "elasticsearch":
        return
    try:
        await get_client().index(
            index=settings.elasticsearch_teacher_index,
            id=str(profile.user_id),
            document=teacher_document(profile, user),
        )
    except Exception as exc:  # pragma: no cover - index sync must not break writes
        logger.warning("Elasticsearch teacher index failed for %s: %s", profile.user_id, exc)


async def delete_teacher(user_id) -> None:
    if settings.search_provider != "elasticsearch":
        return
    try:
        await get_client().delete(
            index=settings.elasticsearch_teacher_index, id=str(user_id), ignore=[404]
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Elasticsearch teacher delete failed for %s: %s", user_id, exc)


async def index_resource(resource) -> None:
    if settings.search_provider != "elasticsearch":
        return
    try:
        await get_client().index(
            index=settings.elasticsearch_resource_index,
            id=str(resource.id),
            document=resource_document(resource),
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Elasticsearch resource index failed for %s: %s", resource.id, exc)


async def delete_resource(resource_id) -> None:
    if settings.search_provider != "elasticsearch":
        return
    try:
        await get_client().delete(
            index=settings.elasticsearch_resource_index, id=str(resource_id), ignore=[404]
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Elasticsearch resource delete failed for %s: %s", resource_id, exc)


async def bulk_index(index: str, documents: Iterable[tuple[str, dict[str, Any]]]) -> int:
    """Bulk index (doc_id, document) pairs. Returns the number of documents sent."""
    client = get_client()
    operations: list[dict[str, Any]] = []
    count = 0
    for doc_id, document in documents:
        operations.append({"index": {"_index": index, "_id": doc_id}})
        operations.append(document)
        count += 1
    if not operations:
        return 0
    response = await client.bulk(operations=operations, refresh=False)
    if response.get("errors"):
        first = next(
            (item for item in response["items"] if item.get("index", {}).get("error")), None
        )
        logger.error("Bulk indexing reported errors, first: %s", first)
    return count


async def refresh_indices() -> None:
    client = get_client()
    await client.indices.refresh(
        index=f"{settings.elasticsearch_teacher_index},{settings.elasticsearch_resource_index}"
    )
