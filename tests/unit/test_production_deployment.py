from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from src.config import LangfuseSettings, OpenSearchSettings, RedisSettings, Settings, TelegramSettings
from src.main import lifespan
from src.services.cache.factory import make_redis_client
from src.services.opensearch.client import OpenSearchClient


def production_config(**overrides) -> dict:
    config = {
        "_env_file": None,
        "environment": "production",
        "opensearch_schema_management_enabled": False,
        "debug": False,
        "api_auth_enabled": True,
        "api_keys": ["production-api-key-with-sufficient-entropy"],
        "api_rate_limit_enabled": True,
        "postgres_database_url": (
            "postgresql+psycopg2://rag_prod:D7m9K2q8N4v6X1z3@db.internal/rag"
            "?sslmode=verify-full"
        ),
        "llm_provider": "openai",
        "openai_api_key": "sk-production-value-with-sufficient-entropy",
        "openai_base_url": "https://api.openai.com/v1",
        "jina_api_key": "jina-production-value-with-sufficient-entropy",
        "opensearch": OpenSearchSettings(
            _env_file=None,
            host="https://search.internal:9200",
            username="rag_service",
            password="Os9xK4v2N7m5Q8z1",
            verify_certs=True,
            ca_certs="/run/secrets/opensearch_ca",
        ),
        "redis": RedisSettings(
            _env_file=None,
            host="redis.internal",
            password="Rd8kP3m7X2v9N5q1",
            ssl=True,
            ssl_ca_certs="/run/secrets/redis_ca",
            ssl_cert_reqs="required",
        ),
        "langfuse": LangfuseSettings(
            _env_file=None,
            enabled=True,
            base_url="https://us.cloud.langfuse.com",
            public_key="pk-production",
            secret_key="lf9K2m7X4v8N1q5Z",
            capture_content=False,
        ),
        "telegram": TelegramSettings(_env_file=None),
    }
    for field_name, model in (
        ("opensearch", OpenSearchSettings),
        ("redis", RedisSettings),
        ("langfuse", LangfuseSettings),
        ("telegram", TelegramSettings),
    ):
        value = overrides.get(field_name)
        if isinstance(value, dict):
            overrides[field_name] = model(_env_file=None, **value)
    config.update(overrides)
    return config


@pytest.mark.parametrize(
    ("override", "expected_error"),
    [
        (
            {"postgres_database_url": "postgresql://rag_prod:weak@db.internal/rag"},
            "POSTGRES_DATABASE_URL",
        ),
        (
            {"opensearch": {"host": "http://search.internal:9200"}},
            "OPENSEARCH__HOST",
        ),
        (
            {"redis": {"host": "redis.internal", "password": "weak", "ssl": False}},
            "Redis TLS",
        ),
        (
            {"openai_base_url": "http://openai-proxy.internal/v1"},
            "OPENAI_BASE_URL",
        ),
        ({"jina_api_key": "changeme"}, "JINA_API_KEY"),
        (
            {
                "langfuse": {
                    "enabled": True,
                    "base_url": "http://langfuse.internal",
                    "public_key": "pk",
                    "secret_key": "weak",
                }
            },
            "LANGFUSE_BASE_URL",
        ),
    ],
)
def test_production_rejects_insecure_dependencies(override, expected_error):
    with pytest.raises(ValidationError, match=expected_error):
        Settings(**production_config(**override))


def test_opensearch_client_enables_verified_tls_and_authentication():
    settings = Settings(**production_config())

    with patch("src.services.opensearch.client.OpenSearch") as constructor:
        OpenSearchClient(settings.opensearch.host, settings)

    options = constructor.call_args.kwargs
    assert options["use_ssl"] is True
    assert options["verify_certs"] is True
    assert options["http_auth"] == ("rag_service", "Os9xK4v2N7m5Q8z1")
    assert options["ca_certs"] == "/run/secrets/opensearch_ca"


def test_redis_client_enables_verified_tls_and_authentication():
    settings = Settings(**production_config())

    with patch("src.services.cache.factory.redis.Redis") as constructor:
        constructor.return_value.ping.return_value = True
        make_redis_client(settings)

    options = constructor.call_args.kwargs
    assert options["ssl"] is True
    assert options["ssl_cert_reqs"] == "required"
    assert options["ssl_ca_certs"] == "/run/secrets/redis_ca"
    assert options["password"] == "Rd8kP3m7X2v9N5q1"


def test_production_settings_repr_hides_credentials():
    settings = Settings(**production_config())
    rendered = repr(settings)

    for secret in (
        "D7m9K2q8N4v6X1z3",
        "sk-production-value-with-sufficient-entropy",
        "jina-production-value-with-sufficient-entropy",
        "Os9xK4v2N7m5Q8z1",
        "Rd8kP3m7X2v9N5q1",
        "lf9K2m7X4v8N1q5Z",
    ):
        assert secret not in rendered


def test_production_ingestion_role_enforces_shared_dependencies_without_api_secrets():
    settings = Settings(
        **production_config(
            service_role="ingestion",
            api_auth_enabled=False,
            api_keys=[],
            api_rate_limit_enabled=False,
            llm_provider="ollama",
            redis=RedisSettings(_env_file=None),
            langfuse=LangfuseSettings(_env_file=None, enabled=False),
        )
    )

    assert settings.service_role == "ingestion"


def test_production_rejects_automatic_opensearch_schema_management():
    with pytest.raises(ValidationError, match="OPENSEARCH_SCHEMA_MANAGEMENT_ENABLED"):
        Settings(**production_config(opensearch_schema_management_enabled=True))


@pytest.mark.anyio
async def test_production_api_startup_does_not_mutate_opensearch_schema():
    settings = Settings(**production_config())
    app = FastAPI()
    database = MagicMock()
    opensearch = MagicMock()
    opensearch.health_check.return_value = True
    opensearch.client.count.return_value = {"count": 3}
    llm = MagicMock(provider_name="openai", default_model=settings.selected_llm_model)
    tracer = MagicMock()

    with (
        patch("src.main.get_settings", return_value=settings),
        patch("src.main.make_database", return_value=database),
        patch("src.main.make_opensearch_client", return_value=opensearch),
        patch("src.main.make_arxiv_client", return_value=MagicMock()),
        patch("src.main.make_pdf_parser_service", return_value=MagicMock()),
        patch("src.main.make_embeddings_service", return_value=MagicMock()),
        patch("src.main.make_llm_client", return_value=llm),
        patch("src.main.make_langfuse_tracer", return_value=tracer),
        patch("src.main.make_cache_client", return_value=MagicMock()),
        patch("src.main.make_agentic_rag_service", return_value=MagicMock()),
        patch("src.main.make_telegram_service", return_value=None),
    ):
        async with lifespan(app):
            pass

    opensearch.setup_indices.assert_not_called()
    tracer.shutdown.assert_called_once()
    database.teardown.assert_called_once()
