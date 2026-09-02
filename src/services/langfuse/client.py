"""Fail-open Langfuse v4 wrapper used by the API and agentic workflow."""

import hashlib
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, Literal, Optional

from langfuse import Langfuse, propagate_attributes
from src.config import Settings

logger = logging.getLogger(__name__)

ObservationType = Literal[
    "span", "agent", "tool", "chain", "retriever", "evaluator", "guardrail", "generation", "embedding"
]


class LangfuseTracer:
    """Small compatibility layer around the Langfuse v4 observation API.

    Telemetry is fail-open: initialization and export failures are logged, but
    never make a business request fail. Raw prompts, queries and answers are
    disabled by default and require ``LANGFUSE_CAPTURE_CONTENT=true``.
    """

    def __init__(self, settings: Settings):
        self.settings = settings.langfuse
        self.client: Optional[Langfuse] = None

        if not (self.settings.enabled and self.settings.public_key and self.settings.secret_key):
            logger.info("Langfuse tracing disabled or missing credentials")
            return

        try:
            self.client = Langfuse(
                public_key=self.settings.public_key,
                secret_key=self.settings.secret_key,
                base_url=self.settings.base_url,
                flush_at=self.settings.flush_at,
                flush_interval=self.settings.flush_interval,
                timeout=self.settings.timeout,
                debug=self.settings.debug,
                tracing_enabled=True,
                environment=settings.environment,
                release=settings.app_version,
                sample_rate=self.settings.sample_rate,
            )
            logger.info("Langfuse v4 tracing initialized (base_url: %s)", self.settings.base_url)
        except Exception as exc:
            logger.error("Failed to initialize Langfuse: %s", exc)

    def safe_content(self, value: Any) -> Any:
        """Return raw content only when explicitly enabled, otherwise a digest."""
        if value is None or self.settings.capture_content:
            return value
        text = value if isinstance(value, str) else repr(value)
        return {
            "redacted": True,
            "chars": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        }

    @contextmanager
    def start_observation(
        self,
        *,
        name: str,
        as_type: ObservationType = "span",
        input_data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        model_parameters: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        """Start a current observation so nested observations inherit its trace."""
        if not self.client:
            yield None
            return

        try:
            manager = self.client.start_as_current_observation(
                name=name,
                as_type=as_type,
                input=input_data,
                metadata=metadata or {},
                model=model,
                model_parameters=model_parameters,
            )
        except Exception as exc:
            logger.error("Failed to create Langfuse observation %s: %s", name, exc)
            yield None
            return

        # Application exceptions must propagate. Langfuse's own context manager
        # records them on the observation before re-raising.
        with manager as observation:
            yield observation

    def start_span(
        self,
        name: str,
        input_data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        as_type: ObservationType = "span",
        model: Optional[str] = None,
        model_parameters: Optional[Dict[str, Any]] = None,
    ):
        """Backward-compatible context-manager entrypoint."""
        return self.start_observation(
            name=name,
            as_type=as_type,
            input_data=input_data,
            metadata=metadata,
            model=model,
            model_parameters=model_parameters,
        )

    @contextmanager
    def trace_attributes(
        self,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_name: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Iterator[None]:
        """Attach indexed trace-level attributes to the current trace."""
        if not self.client:
            yield
            return
        with propagate_attributes(
            user_id=user_id,
            session_id=session_id,
            trace_name=trace_name,
            tags=tags,
        ):
            yield

    def start_generation(
        self,
        name: str,
        model: str,
        input_data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        return self.start_observation(
            name=name,
            as_type="generation",
            input_data=input_data,
            metadata=metadata,
            model=model,
        )

    def create_span(
        self,
        trace: Any,
        name: str,
        input_data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        as_type: ObservationType = "span",
        model: Optional[str] = None,
    ) -> Any:
        """Create a manually-ended child observation for legacy agent nodes."""
        if not self.client:
            return None
        try:
            factory = trace.start_observation if trace is not None else self.client.start_observation
            return factory(
                name=name,
                as_type=as_type,
                input=input_data,
                metadata=metadata or {},
                model=model,
            )
        except Exception as exc:
            logger.error("Failed to create Langfuse child observation %s: %s", name, exc)
            return None

    def update_span(
        self,
        span: Any,
        output: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
    ) -> None:
        """Update an observation without ending it."""
        if not span:
            return
        try:
            values: Dict[str, Any] = {}
            if output is not None:
                values["output"] = output
            if metadata is not None:
                values["metadata"] = metadata
            if level is not None:
                values["level"] = level
            if status_message is not None:
                values["status_message"] = status_message
            if values:
                span.update(**values)
        except Exception as exc:
            logger.error("Failed to update Langfuse observation: %s", exc)

    def end_span(self, span: Any, **updates: Any) -> None:
        if not span:
            return
        try:
            if updates:
                span.update(**updates)
            span.end()
        except Exception as exc:
            logger.error("Failed to end Langfuse observation: %s", exc)

    def update_generation(
        self,
        generation: Any,
        output: Any,
        usage_metadata: Optional[Dict[str, Any]] = None,
        completion_start_time: Optional[datetime] = None,
        finish_reason: Optional[str] = None,
    ) -> None:
        if not generation:
            return
        try:
            values: Dict[str, Any] = {"output": output}
            if usage_metadata:
                values["usage_details"] = {
                    "input": int(usage_metadata.get("prompt_tokens", 0)),
                    "output": int(usage_metadata.get("completion_tokens", 0)),
                    "total": int(usage_metadata.get("total_tokens", 0)),
                }
                timing = {key: value for key, value in usage_metadata.items() if key.endswith("_ms")}
                if timing:
                    values["metadata"] = timing
            if completion_start_time:
                values["completion_start_time"] = completion_start_time
            if finish_reason:
                values.setdefault("metadata", {})["finish_reason"] = finish_reason
            generation.update(**values)
        except Exception as exc:
            logger.error("Failed to update Langfuse generation: %s", exc)

    def get_callback_handler(self, **_metadata: Any):
        if not self.client:
            return None
        try:
            from langfuse.langchain import CallbackHandler

            return CallbackHandler(public_key=self.settings.public_key)
        except Exception as exc:
            logger.error("Failed to create Langfuse CallbackHandler: %s", exc)
            return None

    def get_trace_id(self, _trace: Any = None) -> Optional[str]:
        if not self.client:
            return None
        try:
            return self.client.get_current_trace_id()
        except Exception as exc:
            logger.error("Failed to read current Langfuse trace id: %s", exc)
            return None

    def get_trace_url(self, trace_id: Optional[str] = None) -> Optional[str]:
        if not self.client:
            return None
        try:
            return self.client.get_trace_url(trace_id=trace_id)
        except Exception as exc:
            logger.error("Failed to build Langfuse trace URL: %s", exc)
            return None

    def submit_feedback(
        self,
        trace_id: str,
        score: float,
        name: str = "user-feedback",
        comment: Optional[str] = None,
    ) -> bool:
        if not self.client:
            return False
        try:
            self.client.create_score(trace_id=trace_id, name=name, value=score, comment=comment)
            return True
        except Exception as exc:
            logger.error("Failed to submit Langfuse feedback: %s", exc)
            return False

    def flush(self) -> None:
        if self.client:
            try:
                self.client.flush()
            except Exception as exc:
                logger.error("Failed to flush Langfuse: %s", exc)

    def shutdown(self) -> None:
        if self.client:
            try:
                self.client.shutdown()
            except Exception as exc:
                logger.error("Failed to shut down Langfuse: %s", exc)
