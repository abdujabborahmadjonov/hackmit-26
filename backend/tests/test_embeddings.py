"""Embedding service tests (deterministic provider, no network)."""

from __future__ import annotations

import pytest

from app.services.embedding_service import (
    EmbeddingService,
    HashingEmbeddingProvider,
    OpenAIEmbeddingProvider,
    VoyageEmbeddingProvider,
    build_provider,
    cosine_similarity,
)

DIM = 384


@pytest.fixture
def service() -> EmbeddingService:
    return EmbeddingService(HashingEmbeddingProvider(DIM))


async def test_embedding_has_the_configured_dimension(service):
    vector = await service.generate_embedding("Project-based computer science teaching")
    assert len(vector) == DIM
    assert all(isinstance(value, float) for value in vector)


async def test_embeddings_are_deterministic(service):
    text = "I teach physics through hands-on labs."
    first = await service.generate_embedding(text)
    second = await service.generate_embedding(text)
    assert first == second


async def test_empty_text_still_produces_a_usable_vector(service):
    vector = await service.generate_embedding("")
    assert len(vector) == DIM
    assert any(value != 0 for value in vector), "a zero vector would break cosine distance"


async def test_similar_teaching_styles_are_closer_than_different_ones(service):
    alice = await service.generate_embedding(
        "Project-based, collaborative and hands-on. Students build software in teams."
    )
    bob = await service.generate_embedding(
        "Project-based and collaborative. Students build working apps in pairs."
    )
    carol = await service.generate_embedding(
        "Lecture-based with formal problem sets covering the mathematics of machine learning."
    )

    assert cosine_similarity(alice, bob) > cosine_similarity(alice, carol)
    assert cosine_similarity(alice, bob) > 0.3


async def test_batch_matches_single_calls(service):
    texts = ["socratic seminar discussion", "game based learning in mathematics"]
    batch = await service.generate_embeddings(texts)
    singles = [await service.generate_embedding(text) for text in texts]
    assert batch == singles
    assert await service.generate_embeddings([]) == []


def test_profile_text_includes_every_signal():
    text = EmbeddingService.build_profile_text(
        teaching_style="Project-based.",
        bio="I teach CS.",
        fields_of_expertise=["machine_learning"],
        subjects=["computer_science"],
        teaching_methods=["project_based"],
        education_levels=["high_school"],
    )
    for fragment in (
        "Teaching style: Project-based.",
        "About: I teach CS.",
        "Machine Learning",
        "Computer Science",
        "Project Based",
        "High School",
    ):
        assert fragment in text


def test_resource_text_builder():
    text = EmbeddingService.build_resource_text(
        title="Intro to Functions",
        description="A project pack",
        subject="computer_science",
        education_level="high_school",
        teaching_method="project_based",
        difficulty="beginner",
        tags=["python"],
        required_materials=["laptop", "internet_access"],
    )
    assert "Intro to Functions" in text
    assert "Subject: Computer Science" in text
    assert "Tags: Python" in text
    assert "Required materials: Laptop, Internet Access" in text


def test_provider_falls_back_when_api_key_missing():
    provider = build_provider("openai", DIM, api_key="", model="")
    assert isinstance(provider, HashingEmbeddingProvider)


def test_provider_selection_with_key():
    assert isinstance(build_provider("openai", DIM, api_key="sk-test"), OpenAIEmbeddingProvider)
    assert isinstance(build_provider("voyage", DIM, api_key="pa-test"), VoyageEmbeddingProvider)
    assert isinstance(build_provider("hashing", DIM), HashingEmbeddingProvider)


def test_hosted_providers_request_the_configured_dimension():
    openai = OpenAIEmbeddingProvider(DIM, "sk-test")
    assert openai._payload(["hi"])["dimensions"] == DIM
    voyage = VoyageEmbeddingProvider(DIM, "pa-test")
    assert voyage._payload(["hi"])["output_dimension"] == DIM


def test_cosine_similarity_edge_cases():
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
