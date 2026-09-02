"""Shared deterministic fixtures for unit tests."""

from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from src.services.agents.context import Context
from src.services.agents.models import GradeDocuments, GuardrailScoring
from src.services.agents.nodes.rewrite_query_node import QueryRewriteOutput


class _StructuredLLM:
    def __init__(self, schema: type):
        self.schema = schema

    async def ainvoke(self, _prompt: str):
        if self.schema is GuardrailScoring:
            return GuardrailScoring(score=85, reason="Relevant research query")
        if self.schema is GradeDocuments:
            return GradeDocuments(binary_score="yes", reasoning="Relevant documents")
        if self.schema is QueryRewriteOutput:
            return QueryRewriteOutput(
                rewritten_query="transformer neural network architectures",
                reasoning="Added retrieval-specific terms",
            )
        raise AssertionError(f"Unexpected structured schema: {self.schema}")


class _FakeLLM:
    def with_structured_output(self, schema: type) -> _StructuredLLM:
        return _StructuredLLM(schema)

    async def ainvoke(self, _prompt: str) -> AIMessage:
        return AIMessage(content="A grounded test answer based on the retrieved paper.")


@pytest.fixture
def mock_opensearch_client():
    client = Mock()
    client.search_unified = Mock(
        return_value={
            "total": 2,
            "hits": [
                {
                    "chunk_text": "Transformers are neural network architectures based on self-attention mechanisms.",
                    "arxiv_id": "1706.03762",
                    "title": "Attention Is All You Need",
                    "authors": "Vaswani et al.",
                    "score": 0.95,
                    "section_name": "Introduction",
                },
                {
                    "chunk_text": "BERT uses bidirectional transformer encoders.",
                    "arxiv_id": "1810.04805",
                    "title": "BERT",
                    "authors": "Devlin et al.",
                    "score": 0.90,
                    "section_name": "Method",
                },
            ],
        }
    )
    return client


@pytest.fixture
def mock_jina_embeddings_client():
    client = Mock()
    client.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return client


@pytest.fixture
def mock_ollama_client():
    client = Mock()
    client.get_langchain_model = Mock(return_value=_FakeLLM())
    client.create_llm = Mock(return_value=_FakeLLM())
    return client


@pytest.fixture
def test_context(mock_opensearch_client, mock_ollama_client, mock_jina_embeddings_client):
    return Context(
        ollama_client=mock_ollama_client,
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_jina_embeddings_client,
        langfuse_tracer=None,
        langfuse_enabled=False,
        model_name="test-model",
        max_retrieval_attempts=2,
    )


@pytest.fixture
def sample_human_message():
    return HumanMessage(content="What is machine learning?")


@pytest.fixture
def sample_ai_message():
    return AIMessage(content="Machine learning is a field of AI.")


@pytest.fixture
def sample_tool_message():
    return ToolMessage(
        content=(
            "Transformers use self-attention to model relationships between tokens "
            "and support parallel sequence processing in neural networks."
        ),
        tool_call_id="retrieve_1",
        name="retrieve_papers",
    )
