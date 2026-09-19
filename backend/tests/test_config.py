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


def test_elasticsearch_api_key_is_loaded(monkeypatch) -> None:
    monkeypatch.setenv("ELASTICSEARCH_API_KEY", "id:encoded-key")
    monkeypatch.setenv(
        "ELASTICSEARCH_URL",
        "https://my-vectordb-project-b04eea.es.us-central1.gcp.elastic.cloud:443",
    )
    monkeypatch.setenv("SEARCH_PROVIDER", "elasticsearch")
    loaded = Settings(_env_file=None)
    assert loaded.search_provider == "elasticsearch"
    assert loaded.elasticsearch_api_key == "id:encoded-key"
    assert loaded.elasticsearch_url.endswith("elastic.cloud:443")


def test_elasticsearch_api_key_accepts_elastic_cloud_aliases(monkeypatch) -> None:
    monkeypatch.delenv("ELASTICSEARCH_API_KEY", raising=False)
    monkeypatch.setenv("ELASTIC_API_KEY", "alias-key")
    loaded = Settings(_env_file=None)
    assert loaded.elasticsearch_api_key == "alias-key"


def test_production_flag() -> None:
    assert Settings(_env_file=None, environment="production").is_production is True
    assert Settings(_env_file=None, environment="development").is_production is False


def test_pooler_connect_args(monkeypatch) -> None:
    """Transaction poolers (Supabase:6543, PgBouncer) need prepared statements off."""
    from app.config import settings as live_settings
    from app.database import connect_args_for

    url = "postgresql+asyncpg://user:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres"

    monkeypatch.setattr(live_settings, "db_disable_prepared_statements", False)
    assert connect_args_for(url) == {}

    monkeypatch.setattr(live_settings, "db_disable_prepared_statements", True)
    assert connect_args_for(url) == {
        "prepared_statement_cache_size": 0,
        "statement_cache_size": 0,
    }
    # Irrelevant for non-asyncpg URLs.
    assert connect_args_for("postgresql://user:pass@host/db") == {}


def test_alembic_url_escapes_percent_signs() -> None:
    """A percent-encoded password must survive Alembic's ConfigParser."""
    settings = Settings(
        _env_file=None,
        database_url="postgresql://postgres.ref:p%3Dword%40aws@host.pooler.supabase.com:5432/postgres",
    )
    assert settings.alembic_url == (
        "postgresql+asyncpg://postgres.ref:p%%3Dword%%40aws@host.pooler.supabase.com:5432/postgres"
    )
    # Plain passwords are untouched.
    assert Settings(_env_file=None, database_url="postgresql://u:simple@h/db").alembic_url == (
        "postgresql+asyncpg://u:simple@h/db"
    )


def test_placeholder_password_is_reported_clearly() -> None:
    """The commonest deploy mistake deserves a sentence, not a stack trace."""
    url = "postgresql://postgres:[YOUR-PASSWORD]@db.abcdefgh.supabase.co:5432/postgres"
    with pytest.raises(ValueError, match=r"\[YOUR-PASSWORD\] placeholder"):
        normalise_database_url(url)


def test_ipv6_hosts_still_work() -> None:
    """Brackets are legal around an IPv6 host - do not reject those."""
    assert normalise_database_url("postgresql://user:pass@[::1]:5432/edumatch") == (
        "postgresql+asyncpg://user:pass@[::1]:5432/edumatch"
    )


def test_direct_supabase_host_warns(caplog) -> None:
    """The IPv6-only host is legal but doomed on IPv4 platforms - say so."""
    with caplog.at_level("WARNING"):
        normalise_database_url("postgresql://postgres:secret@db.abcdefgh.supabase.co:5432/postgres")
    assert "Session pooler" in caplog.text

    caplog.clear()
    with caplog.at_level("WARNING"):
        normalise_database_url(
            "postgresql://postgres.abcdefgh:secret@aws-0-us-west-2.pooler.supabase.com:5432/postgres"
        )
    assert caplog.text == ""
