from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from langfuse._client.span import LangfuseSpan
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.llm.protocol import LLMClient
from src.services.opensearch.client import OpenSearchClient


@dataclass
class Context:
    """Runtime context for agent dependencies.

    This contains immutable dependencies that nodes need but don't modify.

    :param llm_client: Provider-neutral client for LLM generation
    :param opensearch_client: Client for document search
    :param embeddings_client: Client for embeddings
    :param langfuse_tracer: Optional tracer for observability
    :param trace: Current Langfuse trace object (if enabled)
    :param langfuse_enabled: Whether Langfuse tracing is enabled
    :param model_name: Model to use for LLM calls
    :param temperature: Temperature for generation
    :param top_k: Number of documents to retrieve
    :param max_retrieval_attempts: Maximum retrieval attempts
    :param guardrail_threshold: Threshold for guardrail validation (0-100)
    """

    llm_client: LLMClient
    opensearch_client: OpenSearchClient
    embeddings_client: JinaEmbeddingsClient
    langfuse_tracer: Optional[LangfuseTracer]
    trace: Optional["LangfuseSpan"] = None
    langfuse_enabled: bool = False
    model_name: str = "llama3.2:1b"
    temperature: float = 0.0
    top_k: int = 3
    use_hybrid: bool = True
    categories: Optional[List[str]] = None
    max_retrieval_attempts: int = 2
    max_embedding_attempts: int = 2
    max_search_attempts: int = 2
    embedding_attempt_timeout_seconds: float = 10.0
    search_attempt_timeout_seconds: float = 5.0
    deadline_monotonic: Optional[float] = None
    generation_reserve_seconds: float = 55.0
    guardrail_threshold: int = 60
