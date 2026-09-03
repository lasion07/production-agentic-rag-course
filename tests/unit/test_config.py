import os

import pytest
from src.config import LangfuseSettings, Settings


def test_settings_initialization():
    """Test settings can be initialized."""
    settings = Settings()

    assert settings.app_version == "0.1.0"
    assert settings.debug is True
    assert settings.environment == "development"
    assert settings.service_name == "rag-api"


def test_settings_postgres_defaults():
    """Test PostgreSQL default configuration."""
    settings = Settings()

    assert "postgresql://" in settings.postgres_database_url
    assert settings.postgres_echo_sql is False
    assert settings.postgres_pool_size == 20
    assert settings.postgres_max_overflow == 0


def test_settings_opensearch_defaults():
    """Test OpenSearch default configuration."""
    settings = Settings()

    assert settings.opensearch.host == "http://localhost:9200"
    assert settings.opensearch.index_name == "arxiv-papers"


def test_settings_ollama_defaults():
    """Test Ollama default configuration."""
    settings = Settings()

    # In Docker environment, this should be ollama service host
    expected_host = "http://ollama:11434" if "OLLAMA_HOST" not in os.environ else settings.ollama_host
    assert settings.ollama_host in ["http://localhost:11434", "http://ollama:11434"]


def test_settings_selects_provider_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4-mini-2026-03-17")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    settings = Settings()

    assert settings.selected_llm_model == "gpt-5.4-mini-2026-03-17"
    assert settings.openai_api_key.get_secret_value() != str(settings.openai_api_key)


def test_global_llm_model_overrides_provider_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "candidate-model")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", '["candidate-model"]')

    assert Settings().selected_llm_model == "candidate-model"


def test_openai_configured_model_must_be_allowlisted(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", '["gpt-5.4-mini-2026-03-17"]')
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(ValueError, match="OPENAI_ALLOWED_MODELS"):
        Settings()


def test_langfuse_official_environment_variable_names(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")

    settings = LangfuseSettings()

    assert settings.public_key == "pk-test"
    assert settings.secret_key == "sk-test"
    assert settings.base_url == "https://us.cloud.langfuse.com"
