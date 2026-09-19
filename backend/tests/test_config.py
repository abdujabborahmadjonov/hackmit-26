"""Configuration handling, especially the deploy-time database URL rewrite."""

from __future__ import annotations

import pytest

from app.config import Settings, normalise_database_url


@pytest.mark.parametrize(
    "given,expected",
    [
        # Heroku / Render style
        (
            "postgres://user:pass@host:5432/edumatch",
            "postgresql+asyncpg://user:pass@host:5432/edumatch",
        ),
        # Supabase / generic libpq
        (
            "postgresql://user:pass@host:5432/edumatch?sslmode=require",
            "postgresql+asyncpg://user:pass@host:5432/edumatch?ssl=require",
        ),
        # Neon adds channel_binding, which asyncpg rejects
        (
            "postgresql://user:pass@ep-x.neon.tech/edumatch?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://user:pass@ep-x.neon.tech/edumatch?ssl=require",
        ),
        # Already correct - left alone
        (
            "postgresql+asyncpg://edumatch:edumatch@localhost:5432/edumatch",
            "postgresql+asyncpg://edumatch:edumatch@localhost:5432/edumatch",
        ),
        # Whitespace from a copy-paste
        (
            "  postgres://user:pass@host/edumatch  ",
            "postgresql+asyncpg://user:pass@host/edumatch",
        ),
    ],
)
def test_database_urls_are_normalised_for_asyncpg(given: str, expected: str) -> None:
    assert normalise_database_url(given) == expected


def test_settings_apply_the_rewrite(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host/edumatch?sslmode=require")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://user:pass@host/edumatch?ssl=require"
    assert settings.sync_database_url == "postgresql://user:pass@host/edumatch?ssl=require"


def test_weights_are_normalised_to_sum_to_one() -> None:
    settings = Settings(_env_file=None, rec_weight_semantic=3.0, rec_weight_expertise=1.0)
    weights = settings.recommendation_weights
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["semantic"] > weights["expertise"]


def test_zero_weights_are_rejected() -> None:
    settings = Settings(
        _env_file=None,
        rec_weight_semantic=0.0,
        rec_weight_expertise=0.0,
        rec_weight_education=0.0,
        rec_weight_teaching_level=0.0,
        rec_weight_location=0.0,
        rec_weight_class_size=0.0,
    )
    with pytest.raises(ValueError):
        _ = settings.recommendation_weights


def test_cors_origins_parsing() -> None:
    assert Settings(_env_file=None, CORS_ORIGINS="*").cors_origins == ["*"]
    assert Settings(_env_file=None, CORS_ORIGINS="http://a.com, http://b.com").cors_origins == [
        "http://a.com",
        "http://b.com",
    ]


def test_production_flag() -> None:
    assert Settings(_env_file=None, environment="production").is_production is True
    assert Settings(_env_file=None, environment="development").is_production is False
