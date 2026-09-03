"""Provider-neutral LLM failure categories."""

from src.exceptions import LLMException


class LLMProviderError(LLMException):
    """A hosted LLM provider rejected or failed a request."""


class LLMProviderAuthenticationError(LLMProviderError):
    """The configured provider credentials are invalid."""


class LLMProviderTimeoutError(LLMProviderError):
    """The provider did not respond before the configured timeout."""
