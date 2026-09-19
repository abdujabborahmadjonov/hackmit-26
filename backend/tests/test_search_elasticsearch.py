"""Elasticsearch engine.

The query-building tests run everywhere. The end-to-end test only runs when a
cluster is actually reachable (docker compose --profile elasticsearch up -d).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from app.config import settings
from app.services import elasticsearch_service as es
from app.services.search_service import (
    ElasticsearchSearchBackend,
    TeacherSearchQuery,
)
from tests.conftest import requires_db

ES_URL = os.getenv("ELASTICSEARCH_URL", settings.elasticsearch_url)


def _cluster_reachable() -> bool:
    async def check() -> bool:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{ES_URL}/_cluster/health")
                return response.status_code == 200
        except Exception:
            return False

    return asyncio.run(check())


requires_elasticsearch = pytest.mark.skipif(
    not _cluster_reachable(),
    reason=(
        f"Elasticsearch not reachable at {ES_URL}. Start it with: "
        "docker compose --profile elasticsearch up -d elasticsearch"
    ),
)


# --------------------------------------------------------------------------- #
# Mappings and documents
# --------------------------------------------------------------------------- #
def test_mappings_use_the_configured_vector_width():
    assert es.TEACHER_MAPPING["properties"]["embedding"]["dims"] == settings.embedding_dim
    assert es.TEACHER_MAPPING["properties"]["embedding"]["similarity"] == "cosine"
    assert es.TEACHER_MAPPING["properties"]["location"]["type"] == "geo_point"
    assert es.RESOURCE_MAPPING["properties"]["tags"]["type"] == "keyword"


def test_teacher_document_shape():
    from app.models.profile import TeacherProfile
    from app.models.user import User

    user = User(id=uuid.uuid4(), first_name="Alice", last_name="Nguyen", email="a@example.com")
    profile = TeacherProfile(
        user_id=user.id,
        bio="I teach CS.",
        teaching_style="Project-based.",
        location_name="Boston, Massachusetts",
        latitude=42.36,
        longitude=-71.06,
        education_levels=["high_school"],
        subjects=["computer_science"],
        fields_of_expertise=["software_engineering"],
        teaching_levels=["beginner"],
        teaching_methods=["project_based"],
        languages=["English"],
        class_size=25,
        years_experience=5,
        average_rating=4.5,
        rating_count=2,
        teaching_style_embedding=[0.1] * settings.embedding_dim,
    )
    document = es.teacher_document(profile, user)
    assert document["location"] == {"lat": 42.36, "lon": -71.06}
    assert document["full_name"] == "Alice Nguyen"
    assert len(document["embedding"]) == settings.embedding_dim


# --------------------------------------------------------------------------- #
# Query construction
# --------------------------------------------------------------------------- #
def test_structured_filters_map_to_term_queries():
    filters = ElasticsearchSearchBackend._teacher_filters(
        TeacherSearchQuery(
            subject="CS",  # synonym, must be canonicalised
            education_level="High School",
            teaching_level="beginner",
            teaching_method="project_based",
            minimum_rating=4.0,
            class_size=25,
            language="English",
            min_years_experience=3,
        )
    )
    dumped = repr(filters)
    assert "'subjects': 'computer_science'" in dumped
    assert {"term": {"education_levels": "high_school"}} in filters
    assert {"term": {"teaching_levels": "beginner"}} in filters
    assert {"range": {"average_rating": {"gte": 4.0}}} in filters
    assert {"range": {"years_experience": {"gte": 3}}} in filters
    # +/- 40% tolerance around the requested class size
    assert {"range": {"class_size": {"gte": 15, "lte": 35}}} in filters


def test_geo_filter_uses_geo_distance():
    filters = ElasticsearchSearchBackend._teacher_filters(
        TeacherSearchQuery(latitude=42.36, longitude=-71.06, radius_km=25)
    )
    assert filters == [
        {"geo_distance": {"distance": "25km", "location": {"lat": 42.36, "lon": -71.06}}}
    ]


def test_sort_clauses():
    assert ElasticsearchSearchBackend._sort_clause(TeacherSearchQuery(sort="rating")) == [
        {"average_rating": "desc"},
        {"rating_count": "desc"},
    ]
    assert ElasticsearchSearchBackend._sort_clause(TeacherSearchQuery(sort="relevance")) is None
    geo_sort = ElasticsearchSearchBackend._sort_clause(
        TeacherSearchQuery(sort="distance", latitude=1.0, longitude=2.0, radius_km=10)
    )
    assert geo_sort[0]["_geo_distance"]["unit"] == "km"


@requires_db
@pytest.mark.integration
async def test_falls_back_to_postgres_when_the_cluster_is_down(monkeypatch, db_session):
    """A dead cluster must degrade to Postgres, not 500 the request."""
    from app.services.search_service import SearchService

    monkeypatch.setattr(settings, "search_provider", "elasticsearch")
    service = SearchService(db_session)
    assert service.elastic is not None

    async def boom(_query):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(service.elastic, "search_teachers", boom)
    outcome = await service.search_teachers(TeacherSearchQuery(limit=5))
    assert outcome.engine == "postgres"


# --------------------------------------------------------------------------- #
# End-to-end (only with a live cluster)
# --------------------------------------------------------------------------- #
@requires_elasticsearch
@pytest.mark.integration
async def test_end_to_end_indexing_and_search(monkeypatch, db_session):

    from app.models.profile import TeacherProfile
    from app.models.user import User
    from app.services.profile_service import refresh_profile_embedding
    from app.services.search_service import SearchService
    from app.utils.auth import hash_password

    monkeypatch.setattr(settings, "search_provider", "elasticsearch")
    monkeypatch.setattr(settings, "elasticsearch_teacher_index", "edumatch_test_teachers")
    monkeypatch.setattr(settings, "elasticsearch_resource_index", "edumatch_test_resources")

    client = es.get_client()
    for index in (settings.elasticsearch_teacher_index, settings.elasticsearch_resource_index):
        await client.indices.delete(index=index, ignore_unavailable=True)
    await es.ensure_indices()

    user = User(
        email=f"es-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("TestPassword123"),
        first_name="Elastic",
        last_name="Teacher",
    )
    db_session.add(user)
    await db_session.flush()
    profile = TeacherProfile(
        user_id=user.id,
        bio="I teach project-based computer science.",
        teaching_style="Students build real software in teams.",
        education_levels=["high_school"],
        subjects=["computer_science", "python"],
        fields_of_expertise=["software_engineering"],
        teaching_levels=["beginner"],
        teaching_methods=["project_based"],
        languages=["English"],
        location_name="Boston, Massachusetts",
        latitude=42.36,
        longitude=-71.06,
        class_size=25,
        years_experience=5,
    )
    await refresh_profile_embedding(profile)
    db_session.add(profile)
    await db_session.commit()

    await es.index_teacher(profile, user)
    await client.indices.refresh(index=settings.elasticsearch_teacher_index)

    outcome = await SearchService(db_session).search_teachers(
        TeacherSearchQuery(query="students building software projects", limit=5)
    )
    assert outcome.engine == "elasticsearch"
    assert any(hit.profile.user_id == profile.user_id for hit in outcome.hits)

    geo = await SearchService(db_session).search_teachers(
        TeacherSearchQuery(latitude=42.36, longitude=-71.06, radius_km=10, limit=5)
    )
    assert any(hit.profile.user_id == profile.user_id for hit in geo.hits)

    await es.delete_teacher(profile.user_id)
    for index in (settings.elasticsearch_teacher_index, settings.elasticsearch_resource_index):
        await client.indices.delete(index=index, ignore_unavailable=True)
    await es.close_client()
