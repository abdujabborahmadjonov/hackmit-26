"""Embedding generation.

The application only ever talks to `EmbeddingService`; swapping providers is an
environment-variable change (EMBEDDING_PROVIDER). The default `hashing`
provider needs no API key and is fully deterministic, which keeps demos and
tests reproducible offline.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from hashlib import blake2b
from collections.abc import Iterable, Sequence
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot produce a vector."""


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
class EmbeddingProvider(Protocol):
    name: str
    dim: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """
    a an and are as at be but by for from has have i in into is it its of on or
    that the their them they this to was were will with we you your my me our
    """.split()
)


class HashingEmbeddingProvider:
    """Deterministic bag-of-ngrams embedding (the "no API key" fallback).

    Feature hashing with a signed hash and sub-linear term-frequency weighting.
    It is not as good as a neural encoder, but it is genuinely semantic at the
    lexical level: two teachers who describe project-based Python teaching land
    close together, and it never changes between runs.
    """

    name = "hashing"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[str]:
        words = [w for w in _TOKEN_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1]
        bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
        return words + bigrams

    def _hash(self, token: str) -> tuple[int, float]:
        digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self.dim
        sign = 1.0 if (value >> 63) & 1 else -1.0
        return index, sign

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        counts = Counter(self._tokens(text))
        if not counts:
            # A zero vector would break cosine distance; use a stable unit vector.
            vector[0] = 1.0
            return vector
        for token, count in counts.items():
            index, sign = self._hash(token)
            weight = 1.0 + math.log(count)
            vector[index] += sign * weight
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:  # pragma: no cover - astronomically unlikely
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]


class _HTTPEmbeddingProvider:
    """Shared plumbing for hosted embedding APIs."""

    name = "http"
    endpoint = ""
    default_model = ""
    dimension_field = "dimensions"

    def __init__(self, dim: int, api_key: str, model: str = "") -> None:
        if not api_key:
            raise EmbeddingError(
                f"EMBEDDING_PROVIDER={self.name} requires EMBEDDING_API_KEY to be set"
            )
        self.dim = dim
        self.api_key = api_key
        self.model = model or self.default_model

    def _payload(self, texts: Sequence[str]) -> dict:
        return {"model": self.model, "input": list(texts), self.dimension_field: self.dim}

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.endpoint, json=self._payload(texts), headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"{self.name} embedding request failed: {exc}") from exc

        try:
            items = sorted(data["data"], key=lambda item: item.get("index", 0))
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError) as exc:  # pragma: no cover - provider contract change
            raise EmbeddingError(f"Unexpected response from {self.name}: {data}") from exc

        for vector in vectors:
            if len(vector) != self.dim:
                raise EmbeddingError(
                    f"{self.name} returned {len(vector)}-dim vectors but EMBEDDING_DIM={self.dim}"
                )
        return vectors


class OpenAIEmbeddingProvider(_HTTPEmbeddingProvider):
    name = "openai"
    endpoint = "https://api.openai.com/v1/embeddings"
    default_model = "text-embedding-3-small"
    dimension_field = "dimensions"


class VoyageEmbeddingProvider(_HTTPEmbeddingProvider):
    name = "voyage"
    endpoint = "https://api.voyageai.com/v1/embeddings"
    default_model = "voyage-3-lite"
    dimension_field = "output_dimension"


def build_provider(
    provider: str | None = None, dim: int | None = None, api_key: str | None = None, model: str | None = None
) -> EmbeddingProvider:
    """Instantiate the configured provider, falling back to `hashing`."""
    provider = (provider or settings.embedding_provider).lower()
    dim = dim or settings.embedding_dim
    api_key = settings.embedding_api_key if api_key is None else api_key
    model = settings.embedding_model if model is None else model

    if provider in ("openai", "voyage") and not api_key:
        logger.warning(
            "EMBEDDING_PROVIDER=%s but no EMBEDDING_API_KEY provided - "
            "falling back to the deterministic 'hashing' provider.",
            provider,
        )
        provider = "hashing"

    if provider == "openai":
        return OpenAIEmbeddingProvider(dim, api_key, model)
    if provider == "voyage":
        return VoyageEmbeddingProvider(dim, api_key, model)
    return HashingEmbeddingProvider(dim)


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class EmbeddingService:
    """Turns profile/resource content into vectors stored in pgvector."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider = provider or build_provider()

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def dim(self) -> int:
        return self._provider.dim

    async def generate_embedding(self, text: str) -> list[float]:
        """Embed a single string."""
        vectors = await self.generate_embeddings([text])
        return vectors[0]

    async def generate_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of strings (one round trip for hosted providers)."""
        if not texts:
            return []
        return await self._provider.embed(texts)

    # --- text builders: the single source of truth for what gets embedded ---
    @staticmethod
    def build_profile_text(
        *,
        teaching_style: str | None = None,
        bio: str | None = None,
        fields_of_expertise: Iterable[str] | None = None,
        subjects: Iterable[str] | None = None,
        teaching_methods: Iterable[str] | None = None,
        education_levels: Iterable[str] | None = None,
    ) -> str:
        """Compose the text that represents a teacher's pedagogy.

        Teaching style and bio come first because they carry the most signal;
        structured attributes are appended as keywords.
        """
        from app.taxonomy import humanize

        parts: list[str] = []
        if teaching_style:
            parts.append(f"Teaching style: {teaching_style}")
        if bio:
            parts.append(f"About: {bio}")
        if teaching_methods:
            parts.append("Methods: " + ", ".join(humanize(m) for m in teaching_methods))
        if fields_of_expertise:
            parts.append("Expertise: " + ", ".join(humanize(f) for f in fields_of_expertise))
        if subjects:
            parts.append("Subjects: " + ", ".join(humanize(s) for s in subjects))
        if education_levels:
            parts.append("Teaches: " + ", ".join(humanize(e) for e in education_levels))
        return "\n".join(parts).strip()

    @staticmethod
    def build_resource_text(
        *,
        title: str,
        description: str | None = None,
        subject: str | None = None,
        education_level: str | None = None,
        teaching_method: str | None = None,
        difficulty: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> str:
        from app.taxonomy import humanize

        parts = [title]
        if description:
            parts.append(description)
        if subject:
            parts.append(f"Subject: {humanize(subject)}")
        if education_level:
            parts.append(f"Level: {humanize(education_level)}")
        if teaching_method:
            parts.append(f"Method: {humanize(teaching_method)}")
        if difficulty:
            parts.append(f"Difficulty: {humanize(difficulty)}")
        if tags:
            parts.append("Tags: " + ", ".join(humanize(t) for t in tags))
        return "\n".join(parts).strip()


def cosine_similarity(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    """Cosine similarity clamped to [0, 1] (negative similarity == no match).

    Accepts lists or numpy arrays - pgvector hands back the latter.
    """
    if a is None or b is None:
        return 0.0
    # Explicit len() checks: numpy arrays have no usable truth value.
    if len(a) == 0 or len(b) == 0 or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        x, y = float(x), float(y)
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / math.sqrt(norm_a * norm_b)))


_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Process-wide singleton (also a FastAPI dependency)."""
    global _service
    if _service is None:
        _service = EmbeddingService()
        logger.info(
            "Embedding provider=%s dim=%s", _service.provider_name, _service.dim
        )
    return _service
