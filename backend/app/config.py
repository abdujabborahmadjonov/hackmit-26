"""Application settings, loaded from the environment (12-factor style)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Secrets come from the environment only."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- app ---
    app_name: str = "EduMatch API"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True

    # --- database ---
    database_url: str = "postgresql+asyncpg://edumatch:edumatch@localhost:5432/edumatch"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- auth ---
    jwt_secret: str = "insecure-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # --- embeddings ---
    embedding_provider: Literal["hashing", "openai", "voyage"] = "hashing"
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dim: int = 384

    # --- search ---
    search_provider: Literal["postgres", "elasticsearch"] = "postgres"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_username: str = ""
    elasticsearch_password: str = ""
    elasticsearch_teacher_index: str = "edumatch_teachers"
    elasticsearch_resource_index: str = "edumatch_resources"
    # When true a failing Elasticsearch falls back to the Postgres backend
    # instead of returning a 5xx. Handy on a hackathon floor with flaky wifi.
    search_fallback_to_postgres: bool = True

    # --- storage ---
    storage_provider: Literal["local", "s3"] = "local"
    storage_local_dir: str = "./storage"
    storage_public_base_url: str = "http://localhost:8000/static/uploads"
    max_upload_size_mb: int = 25
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # --- http ---
    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 20

    # --- recommendation weights ---
    rec_weight_semantic: float = 0.30
    rec_weight_expertise: float = 0.20
    rec_weight_education: float = 0.15
    rec_weight_teaching_level: float = 0.15
    rec_weight_location: float = 0.10
    rec_weight_class_size: float = 0.10
    rec_candidate_pool: int = 300
    rec_default_limit: int = 10
    # Optional JSON override, e.g. {"high_school": {"university": 0.4}}
    education_compatibility_json: str = ""

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_origins_raw.strip()
        if raw in ("", "*"):
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def sync_database_url(self) -> str:
        """psycopg/libpq style URL (used by tooling that cannot speak asyncpg)."""
        return self.database_url.replace("+asyncpg", "")

    @property
    def max_upload_size_bytes(self) -> int:
        return int(self.max_upload_size_mb * 1024 * 1024)

    @property
    def recommendation_weights(self) -> dict[str, float]:
        """Component weights, normalised so they always sum to 1.0."""
        weights = {
            "semantic": self.rec_weight_semantic,
            "expertise": self.rec_weight_expertise,
            "education": self.rec_weight_education,
            "teaching_level": self.rec_weight_teaching_level,
            "location": self.rec_weight_location,
            "class_size": self.rec_weight_class_size,
        }
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Recommendation weights must sum to a positive number")
        return {key: value / total for key, value in weights.items()}

    @property
    def education_compatibility_overrides(self) -> dict[str, dict[str, float]]:
        if not self.education_compatibility_json.strip():
            return {}
        try:
            return json.loads(self.education_compatibility_json)
        except json.JSONDecodeError as exc:  # pragma: no cover - config error path
            raise ValueError(f"EDUCATION_COMPATIBILITY_JSON is not valid JSON: {exc}") from exc


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (also usable as a FastAPI dependency)."""
    return Settings()


settings = get_settings()
