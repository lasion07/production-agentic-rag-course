"""OpenAI Responses API adapter for the provider-neutral LLM contract."""

import logging
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, AuthenticationError
from src.config import Settings
from src.schemas.llm import RAGResponse

from .exceptions import LLMProviderAuthenticationError, LLMProviderError, LLMProviderTimeoutError
from .prompts import RAGPromptBuilder

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Hosted LLM adapter backed by the OpenAI Responses API."""

    provider_name = "openai"

    def __init__(self, settings: Settings):
        api_key = settings.openai_api_key.get_secret_value()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        self.default_model = settings.selected_llm_model
        self.base_url = settings.openai_base_url
        self.timeout = float(settings.openai_timeout)
        self.max_retries = int(settings.openai_max_retries)
        self.reasoning_effort = settings.openai_reasoning_effort
        self.prompt_builder = RAGPromptBuilder()
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    def get_langchain_model(
        self,
        model: str,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> ChatOpenAI:
        """Create the LangChain adapter used by LangGraph nodes."""
        num_predict = kwargs.pop("num_predict", None)
        if num_predict is not None and "max_tokens" not in kwargs:
            kwargs["max_tokens"] = num_predict
        params: Dict[str, Any] = {
            "model": model or self.default_model,
            "api_key": self.client.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "use_responses_api": True,
            "stream_usage": True,
            "store": False,
            **kwargs,
        }
        if self.reasoning_effort == "none":
            params["temperature"] = temperature
        else:
            params["reasoning_effort"] = self.reasoning_effort
        return ChatOpenAI(**params)

    async def health_check(self) -> Dict[str, Any]:
        """Validate credentials and access to the configured model without generation."""
        try:
            model = await self.client.models.retrieve(self.default_model)
            return {
                "status": "healthy",
                "message": "OpenAI API is reachable",
                "provider": self.provider_name,
                "model": model.id,
            }
        except Exception as exc:
            raise self._translate_error(exc, "OpenAI health check failed") from exc

    async def generate(
        self,
        model: Optional[str],
        prompt: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Generate text and normalize it to the existing serving contract."""
        if stream:
            raise ValueError("Use generate_stream() for streaming responses")
        model_name = model or self.default_model
        try:
            response = await self.client.responses.create(
                model=model_name,
                input=prompt,
                max_output_tokens=self._max_output_tokens(kwargs),
                reasoning={"effort": self.reasoning_effort},
                store=False,
            )
            return {
                "response": response.output_text,
                "done": True,
                "done_reason": response.status,
                "usage_metadata": self._usage_metadata(response),
                "provider": self.provider_name,
                "model": model_name,
                "response_id": response.id,
            }
        except Exception as exc:
            raise self._translate_error(exc, "OpenAI generation failed") from exc

    async def generate_stream(
        self,
        model: Optional[str],
        prompt: str,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream text deltas while preserving the existing chunk contract."""
        model_name = model or self.default_model
        try:
            stream = await self.client.responses.create(
                model=model_name,
                input=prompt,
                max_output_tokens=self._max_output_tokens(kwargs),
                reasoning={"effort": self.reasoning_effort},
                store=False,
                stream=True,
            )
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield {"response": event.delta, "done": False}
                elif event.type == "response.completed":
                    response = event.response
                    yield {
                        "response": "",
                        "done": True,
                        "done_reason": response.status,
                        "usage_metadata": self._usage_metadata(response),
                        "provider": self.provider_name,
                        "model": model_name,
                        "response_id": response.id,
                    }
        except Exception as exc:
            raise self._translate_error(exc, "OpenAI streaming generation failed") from exc

    async def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
        use_structured_output: bool = False,
    ) -> Dict[str, Any]:
        """Generate a grounded RAG response using the configured OpenAI model."""
        model_name = model or self.default_model
        prompt = self.prompt_builder.create_rag_prompt(query, chunks)
        try:
            if use_structured_output:
                response = await self.client.responses.parse(
                    model=model_name,
                    input=prompt,
                    text_format=RAGResponse,
                    max_output_tokens=128,
                    reasoning={"effort": self.reasoning_effort},
                    store=False,
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise LLMProviderError("OpenAI returned no structured RAG response")
                result = parsed.model_dump()
                result["usage_metadata"] = self._usage_metadata(response)
                result["finish_reason"] = response.status
                return result

            response = await self.generate(model=model_name, prompt=prompt, num_predict=128)
            if not response:
                raise LLMProviderError("OpenAI returned no RAG response")
            return {
                "answer": response["response"],
                "sources": self._sources(chunks),
                "confidence": "medium",
                "citations": self._citations(chunks),
                "usage_metadata": response.get("usage_metadata", {}),
                "finish_reason": response.get("done_reason"),
            }
        except LLMProviderError:
            raise
        except Exception as exc:
            raise self._translate_error(exc, "OpenAI RAG generation failed") from exc

    async def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a grounded RAG answer."""
        prompt = self.prompt_builder.create_rag_prompt(query, chunks)
        async for chunk in self.generate_stream(model=model, prompt=prompt, num_predict=128):
            yield chunk

    @staticmethod
    def _max_output_tokens(kwargs: Dict[str, Any]) -> int:
        return int(kwargs.get("max_output_tokens") or kwargs.get("max_tokens") or kwargs.get("num_predict") or 128)

    @staticmethod
    def _usage_metadata(response: Any) -> Dict[str, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        result = {
            "prompt_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }
        details = getattr(usage, "input_tokens_details", None)
        cached_tokens = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        if cached_tokens:
            result["cached_tokens"] = cached_tokens
        return result

    @staticmethod
    def _sources(chunks: List[Dict[str, Any]]) -> List[str]:
        sources: List[str] = []
        for arxiv_id in OpenAIClient._citations(chunks):
            clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
            sources.append(f"https://arxiv.org/pdf/{clean_id}.pdf")
        return sources

    @staticmethod
    def _citations(chunks: List[Dict[str, Any]]) -> List[str]:
        return list(dict.fromkeys(chunk["arxiv_id"] for chunk in chunks if chunk.get("arxiv_id")))[:5]

    @staticmethod
    def _translate_error(exc: Exception, message: str) -> LLMProviderError:
        if isinstance(exc, AuthenticationError):
            return LLMProviderAuthenticationError(message)
        if isinstance(exc, APITimeoutError):
            return LLMProviderTimeoutError(message)
        if isinstance(exc, APIConnectionError):
            return LLMProviderError(f"{message}: connection error")
        if isinstance(exc, APIStatusError):
            return LLMProviderError(f"{message}: HTTP {exc.status_code}")
        if isinstance(exc, LLMProviderError):
            return exc
        return LLMProviderError(f"{message}: {type(exc).__name__}")
