"""Select an LLM provider without leaking provider details to consumers."""

from functools import lru_cache

from src.config import get_settings
from src.services.ollama.client import OllamaClient

from .openai_client import OpenAIClient
from .protocol import LLMClient


@lru_cache(maxsize=1)
def make_llm_client() -> LLMClient:
    """Build the configured singleton LLM client."""
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIClient(settings)
    if settings.llm_provider == "ollama":
        return OllamaClient(settings)
    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
