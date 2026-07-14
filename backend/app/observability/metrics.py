from __future__ import annotations

from collections.abc import Iterable

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from app.services.tools.trace import ToolCallTrace


REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "illiniguideserve_http_requests_total",
    "HTTP requests handled by the application.",
    ("method", "path", "status"),
    registry=REGISTRY,
)
HTTP_ERRORS = Counter(
    "illiniguideserve_http_request_errors_total",
    "HTTP requests that returned a client or server error.",
    ("method", "path", "status"),
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "illiniguideserve_http_request_latency_seconds",
    "HTTP request latency in seconds.",
    ("method", "path"),
    registry=REGISTRY,
)
TOOL_CALLS = Counter(
    "illiniguideserve_tool_calls_total",
    "Tool calls observed in the advising pipeline.",
    ("tool", "status"),
    registry=REGISTRY,
)
TOOL_LATENCY = Histogram(
    "illiniguideserve_tool_latency_seconds",
    "Tool latency in seconds.",
    ("tool",),
    registry=REGISTRY,
)
RETRIEVAL_LATENCY = Histogram(
    "illiniguideserve_retrieval_latency_seconds",
    "Course-document retrieval latency in seconds.",
    ("retriever",),
    registry=REGISTRY,
)
LLM_LATENCY = Histogram(
    "illiniguideserve_llm_latency_seconds",
    "LLM generation latency in seconds.",
    ("backend", "model"),
    registry=REGISTRY,
)
STREAM_TTFT = Histogram(
    "illiniguideserve_stream_ttft_seconds",
    "Time from stream start until the first non-empty content chunk.",
    ("backend", "model"),
    registry=REGISTRY,
)


def observe_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record one completed HTTP request using bounded route labels."""
    labels = {
        "method": method,
        "path": path,
        "status": str(status_code),
    }
    HTTP_REQUESTS.labels(**labels).inc()
    if status_code >= 400:
        HTTP_ERRORS.labels(**labels).inc()
    HTTP_LATENCY.labels(method=method, path=path).observe(
        max(0.0, duration_seconds)
    )


def observe_tool_calls(calls: Iterable[ToolCallTrace]) -> None:
    """Record tool trace entries after a request finishes its pipeline."""
    for call in calls:
        duration_seconds = max(0.0, call.latency_ms / 1000.0)
        TOOL_CALLS.labels(tool=call.tool_name, status=call.status).inc()
        TOOL_LATENCY.labels(tool=call.tool_name).observe(duration_seconds)
        if call.tool_name == "search_course_docs":
            RETRIEVAL_LATENCY.labels(retriever="course_docs").observe(
                duration_seconds
            )
        if call.tool_name in {"llm_generate", "llm_generate_stream"}:
            LLM_LATENCY.labels(
                backend=str(call.arguments.get("backend", "unknown")),
                model=str(call.arguments.get("model", "unknown")),
            ).observe(duration_seconds)


def observe_stream_ttft(
    *,
    backend: str,
    model: str,
    duration_seconds: float,
) -> None:
    """Record time-to-first-token for a stream that emitted content."""
    STREAM_TTFT.labels(backend=backend, model=model).observe(
        max(0.0, duration_seconds)
    )


def render_metrics() -> bytes:
    """Return the registry in Prometheus text exposition format."""
    return generate_latest(REGISTRY)


__all__ = [
    "observe_http_request",
    "observe_stream_ttft",
    "observe_tool_calls",
    "render_metrics",
]
