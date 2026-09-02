from contextlib import contextmanager

from src.services.langfuse.tracer import RAGTracer


class FakeSpan:
    def __init__(self):
        self.outputs = []
        self.end_calls = 0

    def update(self, **kwargs):
        self.outputs.append(kwargs)

    def end(self):
        self.end_calls += 1


class FakeLangfuseTracer:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.spans = []
        self.calls = []

    def safe_content(self, value):
        return {"redacted": True, "chars": len(value)}

    @contextmanager
    def trace_attributes(self, **_kwargs):
        yield

    @contextmanager
    def start_span(self, **kwargs):
        self.calls.append(kwargs)
        if not self.enabled:
            yield None
            return
        span = FakeSpan()
        self.spans.append(span)
        try:
            yield span
        finally:
            span.end()

    def update_span(self, span, **kwargs):
        if span:
            span.update(**kwargs)

    def update_generation(self, span, **kwargs):
        if span:
            span.update(**kwargs)


def test_disabled_tracing_is_noop():
    tracer = RAGTracer(FakeLangfuseTracer(enabled=False))

    with tracer.trace_request("user", "query") as trace:
        assert trace is None
        with tracer.trace_search(trace, "query", 3) as span:
            assert span is None
            tracer.end_search(span, [], [], 0)


def test_enabled_tracing_updates_and_ends_spans():
    client = FakeLangfuseTracer(enabled=True)
    tracer = RAGTracer(client)

    with tracer.trace_request("user", "query") as trace:
        with tracer.trace_search(trace, "query", 3) as span:
            tracer.end_search(span, [{"chunk_text": "x"}], ["paper-1"], 1)
        tracer.end_request(trace, "answer", 0.25)

    assert len(client.spans) == 2
    assert all(span.end_calls == 1 for span in client.spans)
    assert [call["as_type"] for call in client.calls] == ["chain", "retriever"]


def test_cache_error_is_warning_but_request_can_stay_ok():
    client = FakeLangfuseTracer(enabled=True)
    tracer = RAGTracer(client)

    with tracer.trace_request("user", "query") as trace:
        with tracer.trace_cache("lookup") as cache_span:
            tracer.end_cache(cache_span, "error")
        tracer.end_request(trace, "answer", 0.1)

    cache_update = client.spans[1].outputs[-1]
    request_update = client.spans[0].outputs[-1]
    assert cache_update["level"] == "WARNING"
    assert request_update["output"]["status"] == "ok"
