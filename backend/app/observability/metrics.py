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
        TOOL_CALLS.labels(tool=call.tool_name, status=call.status).inc()
        TOOL_LATENCY.labels(tool=call.tool_name).observe(
            max(0.0, call.latency_ms / 1000.0)
        )


def render_metrics() -> bytes:
    """Return the registry in Prometheus text exposition format."""
    return generate_latest(REGISTRY)


__all__ = [
    "observe_http_request",
    "observe_tool_calls",
    "render_metrics",
]
