from types import SimpleNamespace
from unittest.mock import patch

import pytest
from src.services.llm.factory import make_llm_client


@pytest.fixture(autouse=True)
def clear_factory_cache():
    make_llm_client.cache_clear()
    yield
    make_llm_client.cache_clear()


def test_factory_selects_openai():
    settings = SimpleNamespace(llm_provider="openai")
    with (
        patch("src.services.llm.factory.get_settings", return_value=settings),
        patch("src.services.llm.factory.OpenAIClient") as openai_client,
    ):
        result = make_llm_client()

    assert result is openai_client.return_value
    openai_client.assert_called_once_with(settings)


def test_factory_keeps_ollama_compatible():
    settings = SimpleNamespace(llm_provider="ollama")
    with (
        patch("src.services.llm.factory.get_settings", return_value=settings),
        patch("src.services.llm.factory.OllamaClient") as ollama_client,
    ):
        result = make_llm_client()

    assert result is ollama_client.return_value
    ollama_client.assert_called_once_with(settings)


def test_factory_rejects_unknown_provider():
    settings = SimpleNamespace(llm_provider="unknown")
    with patch("src.services.llm.factory.get_settings", return_value=settings):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            make_llm_client()
