from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from src.services.llm.openai_client import OpenAIClient


def settings(**overrides):
    values = {
        "openai_api_key": SecretStr("test-key"),
        "selected_llm_model": "gpt-5.4-mini-2026-03-17",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_timeout": 12,
        "openai_max_retries": 2,
        "openai_reasoning_effort": "low",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def response(text="answer"):
    return SimpleNamespace(
        id="resp-1",
        output_text=text,
        output_parsed=None,
        status="completed",
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=4,
            total_tokens=14,
            input_tokens_details=SimpleNamespace(cached_tokens=3),
        ),
    )


class FakeStream:
    """Minimal async iterator matching the Responses streaming contract."""

    def __init__(self, events):
        self._events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def test_requires_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIClient(settings(openai_api_key=SecretStr("")))


def test_langchain_adapter_uses_responses_api_without_exposing_key():
    with patch("src.services.llm.openai_client.AsyncOpenAI"), patch(
        "src.services.llm.openai_client.ChatOpenAI"
    ) as chat_openai:
        client = OpenAIClient(settings())
        model = client.get_langchain_model("gpt-5.4-mini-2026-03-17", temperature=0.7, num_predict=32)

    assert model is chat_openai.return_value
    kwargs = chat_openai.call_args.kwargs
    assert kwargs["use_responses_api"] is True
    assert kwargs["reasoning_effort"] == "low"
    assert "temperature" not in kwargs
    assert kwargs["store"] is False
    assert kwargs["max_tokens"] == 32
    assert "num_predict" not in kwargs


@pytest.mark.asyncio
async def test_generate_normalizes_response_and_usage():
    with patch("src.services.llm.openai_client.AsyncOpenAI") as sdk:
        sdk.return_value.responses.create = AsyncMock(return_value=response())
        client = OpenAIClient(settings())
        result = await client.generate(None, "question", num_predict=128)

    assert result["response"] == "answer"
    assert result["provider"] == "openai"
    assert result["usage_metadata"] == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
        "cached_tokens": 3,
    }
    call = sdk.return_value.responses.create.await_args.kwargs
    assert call["model"] == "gpt-5.4-mini-2026-03-17"
    assert call["max_output_tokens"] == 128
    assert call["store"] is False


@pytest.mark.asyncio
async def test_generate_stream_normalizes_text_and_completion_events():
    completed = response("")
    events = FakeStream(
        [
            SimpleNamespace(type="response.output_text.delta", delta="hello"),
            SimpleNamespace(type="response.output_text.delta", delta=" world"),
            SimpleNamespace(type="response.completed", response=completed),
        ]
    )
    with patch("src.services.llm.openai_client.AsyncOpenAI") as sdk:
        sdk.return_value.responses.create = AsyncMock(return_value=events)
        client = OpenAIClient(settings())
        chunks = [chunk async for chunk in client.generate_stream(None, "question")]

    assert [chunk["response"] for chunk in chunks] == ["hello", " world", ""]
    assert chunks[-1]["done"] is True
    assert chunks[-1]["provider"] == "openai"
    assert chunks[-1]["usage_metadata"]["total_tokens"] == 14
    assert sdk.return_value.responses.create.await_args.kwargs["stream"] is True


@pytest.mark.asyncio
async def test_health_check_reports_provider_and_model():
    with patch("src.services.llm.openai_client.AsyncOpenAI") as sdk:
        sdk.return_value.models.retrieve = AsyncMock(return_value=SimpleNamespace(id="model-snapshot"))
        result = await OpenAIClient(settings()).health_check()

    assert result == {
        "status": "healthy",
        "message": "OpenAI API is reachable",
        "provider": "openai",
        "model": "model-snapshot",
    }


@pytest.mark.asyncio
async def test_rag_answer_preserves_sources_and_usage():
    with patch("src.services.llm.openai_client.AsyncOpenAI") as sdk:
        sdk.return_value.responses.create = AsyncMock(return_value=response("grounded answer"))
        client = OpenAIClient(settings())
        result = await client.generate_rag_answer(
            query="question",
            chunks=[{"arxiv_id": "1234.5678v2", "chunk_text": "evidence"}],
        )

    assert result["answer"] == "grounded answer"
    assert result["sources"] == ["https://arxiv.org/pdf/1234.5678.pdf"]
    assert result["citations"] == ["1234.5678v2"]
    assert result["usage_metadata"]["total_tokens"] == 14
