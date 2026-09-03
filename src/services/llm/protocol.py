"""Structural contract shared by local and hosted LLM providers."""

from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel


@runtime_checkable
class LLMClient(Protocol):
    """Minimum interface consumed by serving and agentic RAG."""

    provider_name: str
    default_model: str

    def get_langchain_model(
        self,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> BaseChatModel: ...

    async def health_check(self) -> Dict[str, Any]: ...

    async def generate(
        self,
        model: Optional[str],
        prompt: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]: ...

    def generate_stream(
        self,
        model: Optional[str],
        prompt: str,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]: ...

    async def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
        use_structured_output: bool = False,
    ) -> Dict[str, Any]: ...

    def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]: ...
