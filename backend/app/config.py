"""Application settings, loaded from the environment (12-factor style)."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq accepts these; asyncpg rejects them outright. Managed Postgres
# providers (Neon, Supabase, Render, Heroku) put them in the URL they hand you.
_LIBPQ_ONLY_PARAMS = frozenset(
    {"channel_binding", "options", "target_session_attrs", "connect_timeout", "gssencmode"}
)


def normalise_database_url(url: str) -> str:
    """Turn any Postgres URL into one the asyncpg driver accepts.

    Managed databases hand out `postgres://user:pass@host/db?sslmode=require`;
    SQLAlchemy needs the `+asyncpg` scheme and asyncpg spells the TLS option
    `ssl`. Doing this here means a deploy is a copy-paste, not a debugging
    session.
    """
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    if "[YOUR-PASSWORD]" in url or "[PASSWORD]" in url:
        raise ValueError(
            "DATABASE_URL still contains the [YOUR-PASSWORD] placeholder. Paste the "
            "real password from Supabase (Connect -> Session pooler, or Settings -> "
            "Database -> Reset database password)."
        )

    try:
        parts = urlsplit(url)
        _ = parts.port  # accessing it is what validates the host and port
    except ValueError as exc:
        raise ValueError(
            f"DATABASE_URL could not be parsed ({exc}). If the password contains "
            "@ : / ? # or %, percent-encode it - or generate one without them."
        ) from exc

    # Supabase's direct host has no A record. It works from a laptop and fails
    # on every IPv4-only platform (Render, Fly, Railway) with a DNS error that
    # says nothing about the cause.
    if re.match(r"^db\.[a-z0-9]+\.supabase\.co$", parts.hostname or ""):
        logging.getLogger(__name__).warning(
            "DATABASE_URL uses Supabase's direct connection (%s), which is "
            "IPv6-only. If this host is IPv4-only the connection will fail with "
            "'Name or service not known'. Use Connect -> Session pooler instead.",
            parts.hostname,
        )

    if not parts.query:
        return url

    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered == "sslmode":
            kept.append(("ssl", value))
        elif lowered in _LIBPQ_ONLY_PARAMS:
            continue
        else:
            kept.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(kept)))


class Settings(BaseSettings):
    """All runtime configuration. Secrets come from the environment only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
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
    # Transaction-mode connection poolers (Supabase Supavisor on port 6543,
    # PgBouncer) multiplex one server session across clients, which breaks
    # server-side prepared statements. Set this when connecting through one.
    db_disable_prepared_statements: bool = False

    # --- auth ---
    jwt_secret: str = "insecure-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # --- embeddings ---
    embedding_provider: Literal["hashing", "openai", "voyage"] = "hashing"
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dim: int = 384

    # --- generative features (optional) ---
    # An Anthropic API key. Unset means the brief and syllabus import are
    # disabled and their endpoints return 503; nothing else changes.
    llm_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("LLM_API_KEY", "ANTHROPIC_API_KEY"),
    )

    # --- speech (optional) ---
    # A Deepgram API key. Unset means mentors fall back to the browser's own
    # speech synthesis, which works but sounds markedly worse.
    deepgram_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("DEEPGRAM_API_KEY", "DG_API_KEY"),
    )
    # Aura-2, British, warm baritone - see https://developers.deepgram.com/docs/tts-models
    deepgram_tts_model: str = "aura-2-draco-en"
    # One request per spoken sentence, so this is per reply rather than per turn.
    tts_rate_limit_per_minute: int = 120

    # --- search ---
    search_provider: Literal["postgres", "elasticsearch"] = "postgres"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("ELASTICSEARCH_API_KEY", "ELASTIC_API_KEY", "ES_API_KEY"),
    )
    elasticsearch_username: str = ""
    elasticsearch_password: str = Field(default="", repr=False)
    elasticsearch_teacher_index: str = "edumatch_teachers"
    elasticsearch_resource_index: str = "edumatch_resources"
    # When true a failing Elasticsearch falls back to the Postgres backend
    # instead of returning a 5xx. Handy on a hackathon floor with flaky wifi.
    search_fallback_to_postgres: bool = True

    # --- storage ---
    storage_provider: Literal["local", "s3", "supabase"] = "local"
    storage_local_dir: str = "./storage"
    storage_public_base_url: str = "http://localhost:8000/static/uploads"
    max_upload_size_mb: int = 25
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    # Supabase Storage (STORAGE_PROVIDER=supabase). Plain REST, so no SDK and
    # no extra dependency. The service key is a secret - server side only.
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "resources"

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

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        return normalise_database_url(value)

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
    def alembic_url(self) -> str:
        """The URL as Alembic needs it.

        Alembic stores it in a ConfigParser, which treats `%` as interpolation
        syntax - and a percent-encoded password is full of them.
        """
        return self.database_url.replace("%", "%%")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

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


def orphaned_env_lines(env_file: str = ".env") -> list[int]:
    """Line numbers in .env that hold a value with no NAME= in front of it.

    `echo 'KEY=value' >> .env` loses the name easily - a stray quote, a partial
    paste - and the result is a file that looks right, parses without error,
    and silently ignores the setting. Worth one warning at startup rather than
    half an hour wondering why a key is not picked up.
    """
    path = Path(env_file)
    if not path.exists():
        return []
    orphans = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" not in stripped:
            orphans.append(number)
    return orphans


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (also usable as a FastAPI dependency)."""
    return Settings()


settings = get_settings()
