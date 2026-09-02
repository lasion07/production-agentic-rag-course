"""Week 6.3 lab: trace trees, latency breakdown, and alert evaluation."""

from dataclasses import dataclass, field


@dataclass
class Span:
    name: str
    duration_seconds: float
    status: str = "ok"
    attributes: dict[str, object] = field(default_factory=dict)
    children: list["Span"] = field(default_factory=list)


@dataclass
class AlertResult:
    name: str
    firing: bool
    severity: str
    observed: float
    threshold: float
    reason: str


def render_span(span: Span, prefix: str = "", is_last: bool = True) -> list[str]:
    connector = "└─" if is_last else "├─"
    attributes = " ".join(f"{key}={value}" for key, value in span.attributes.items())
    suffix = f" {attributes}" if attributes else ""
    lines = [f"{prefix}{connector} {span.name}: {span.duration_seconds:.2f}s status={span.status}{suffix}"]
    child_prefix = prefix + ("   " if is_last else "│  ")
    for index, child in enumerate(span.children):
        lines.extend(render_span(child, child_prefix, index == len(span.children) - 1))
    return lines


def evaluate_rate_alert(
    *,
    name: str,
    failures: int,
    total: int,
    threshold: float,
    minimum_traffic: int,
    severity: str,
    reason: str,
) -> AlertResult:
    observed = failures / total if total else 0.0
    firing = total >= minimum_traffic and observed > threshold
    return AlertResult(name, firing, severity, observed, threshold, reason)


def evaluate_trace_gap(*, requests: int, traces: int) -> AlertResult:
    gap = max(requests - traces, 0) / requests if requests else 0.0
    return AlertResult(
        name="trace_delivery_gap",
        firing=requests >= 100 and gap > 0.05,
        severity="warning",
        observed=gap,
        threshold=0.05,
        reason="No sampling is configured; missing traces indicate telemetry loss",
    )


def main() -> None:
    trace = Span(
        name="rag_request",
        duration_seconds=50.00,
        attributes={"cache_result": "error", "search_mode": "hybrid"},
        children=[
            Span("cache_lookup", 0.03, status="error", attributes={"fail_open": True}),
            Span("query_embedding", 0.90),
            Span("search_retrieval", 0.40, attributes={"chunks": 3}),
            Span("context_construction", 0.10, attributes={"evidence_tokens": 4200}),
            Span("llm_generation", 48.00, attributes={"model": "llama3.2:1b"}),
            Span("output_validation", 0.20, attributes={"citation_valid": True}),
        ],
    )

    print("representative_trace")
    print(f"{trace.name}: {trace.duration_seconds:.2f}s status={trace.status}")
    for index, child in enumerate(trace.children):
        print("\n".join(render_span(child, "", index == len(trace.children) - 1)))

    child_total = sum(child.duration_seconds for child in trace.children)
    unaccounted = trace.duration_seconds - child_total
    generation_share = next(child.duration_seconds for child in trace.children if child.name == "llm_generation")
    print(f"\nchild_span_total={child_total:.2f}s")
    print(f"unaccounted_overhead={unaccounted:.2f}s")
    print(f"representative_generation_share={generation_share / trace.duration_seconds:.1%}")

    requests = 1_000
    errors = 30
    redis_errors = 400
    traces_received = 700

    alerts = [
        evaluate_rate_alert(
            name="rag_error_rate",
            failures=errors,
            total=requests,
            threshold=0.02,
            minimum_traffic=50,
            severity="critical",
            reason="User-facing RAG failures exceed the error budget",
        ),
        evaluate_rate_alert(
            name="redis_error_rate",
            failures=redis_errors,
            total=requests,
            threshold=0.10,
            minimum_traffic=50,
            severity="warning",
            reason="Cache is degraded, but fail-open requests still succeed",
        ),
        evaluate_trace_gap(requests=requests, traces=traces_received),
    ]

    print("\naggregate_snapshot")
    print("requests=1000 errors=30 llm_timeouts=25 opensearch_errors=5")
    print("p95_total=52.0s p95_generation=48.0s p95_embedding=0.9s p95_search=0.4s")
    print("p95_generation_share_indicator=92.3% (percentiles are not strictly additive)")
    print("redis_errors=400 fail_open_successes=400 traces_received=700 sampling=off")

    print("\nalert_evaluation")
    for alert in alerts:
        state = "FIRING" if alert.firing else "OK"
        print(
            f"{alert.name}: state={state} severity={alert.severity} "
            f"observed={alert.observed:.1%} threshold={alert.threshold:.1%} reason={alert.reason}"
        )


if __name__ == "__main__":
    main()
