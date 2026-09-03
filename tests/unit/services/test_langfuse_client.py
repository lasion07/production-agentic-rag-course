from types import SimpleNamespace
from unittest.mock import MagicMock

from src.config import LangfuseSettings, Settings
from src.services.langfuse import client as client_module


def _settings(capture_content: bool = False) -> Settings:
    langfuse = LangfuseSettings(
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
        LANGFUSE_BASE_URL="https://us.cloud.langfuse.com",
        LANGFUSE_CAPTURE_CONTENT=capture_content,
    )
    return Settings(langfuse=langfuse)


def test_v4_client_uses_base_url_and_environment(monkeypatch):
    sdk = MagicMock()
    monkeypatch.setattr(client_module, "Langfuse", sdk)

    tracer = client_module.LangfuseTracer(_settings())

    assert tracer.client is sdk.return_value
    kwargs = sdk.call_args.kwargs
    assert kwargs["base_url"] == "https://us.cloud.langfuse.com"
    assert kwargs["environment"] == "development"
    assert kwargs["tracing_enabled"] is True
    assert kwargs["mask_otel_spans"] is client_module._mask_trace_content


def test_raw_content_is_redacted_by_default():
    tracer = client_module.LangfuseTracer.__new__(client_module.LangfuseTracer)
    tracer.settings = _settings().langfuse

    value = tracer.safe_content("private query")

    assert value["redacted"] is True
    assert value["chars"] == 13
    assert "private query" not in str(value)


def test_otel_mask_redacts_langchain_content_attributes():
    identifier = object()
    params = SimpleNamespace(
        spans={
            identifier: SimpleNamespace(
                attributes={
                    "langfuse.observation.input": "private prompt",
                    "langfuse.observation.model.name": "gpt-5.4-mini-2026-03-17",
                }
            )
        }
    )

    result = client_module._mask_trace_content(params=params)
    patch = result.span_patches[identifier]

    assert "private prompt" not in patch.set_attributes["langfuse.observation.input"]
    assert '"redacted":true' in patch.set_attributes["langfuse.observation.input"]
    assert "langfuse.observation.model.name" not in patch.set_attributes
