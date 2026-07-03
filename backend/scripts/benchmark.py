"""Concurrent load test for the IlliniGuide chat endpoints.

Measures four things separately:

- TTFT (time-to-first-token) — only meaningful for the streaming endpoint;
  the moment the first ``content`` SSE event lands at the client. For the
  blocking endpoint this equals total latency.
- Total latency — from request send to full response (or end of stream).
- Aggregate output throughput in tokens/sec (approximate, based on the
  completion_tokens number reported by the LLM backend).
- Error rate — HTTP non-2xx, timeouts, malformed SSE.

Percentiles reported: p50 / p95 / p99. A percentile column is more useful
than an average because it exposes tail behavior, which is what actual
users experience.

Prompt selection cycles across four advising templates to exercise the
different pipeline paths (course_qa / comparison / recommendation /
prereq_check) and to make sure prefix caching in vLLM does not artificially
inflate TTFT results by always hitting the same prompt prefix.

Usage:
    # Warmup 3, then 50 requests at 10 concurrency against the streaming path
    python -m scripts.benchmark --endpoint stream --concurrency 10 --total-requests 50

    # Same load on the blocking endpoint for a side-by-side comparison
    python -m scripts.benchmark --endpoint chat --concurrency 10 --total-requests 50

    # Cheap single-user baseline (useful for TTFT lower bound)
    python -m scripts.benchmark --endpoint stream --concurrency 1 --total-requests 5
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from time import perf_counter

import httpx


SAMPLE_PROMPTS: tuple[str, ...] = (
    "What is ECE 391 about?",
    "Compare ECE 408 and CS 433 for AI infra",
    "What courses are good for AI infrastructure?",
    "Am I ready for ECE 408?",
)


@dataclass
class RequestResult:
    prompt: str
    endpoint: str
    ttft_ms: int | None = None
    total_latency_ms: int | None = None
    completion_tokens: int | None = None
    error: str | None = None
    counted: bool = True  # False for warmup


@dataclass
class BenchmarkConfig:
    backend_url: str
    endpoint: str  # "stream" or "chat"
    concurrency: int
    total_requests: int
    warmup: int
    request_timeout: float
    debug: bool = False


def _parse_args() -> BenchmarkConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-url",
        default=os.getenv("BACKEND_URL", "http://localhost:8001"),
    )
    parser.add_argument(
        "--endpoint", choices=("stream", "chat"), default="stream"
    )
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--total-requests", type=int, default=50)
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="First N requests are executed but excluded from the aggregation.",
    )
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ask backend to include debug_trace (adds latency; off by default).",
    )
    args = parser.parse_args()
    return BenchmarkConfig(
        backend_url=args.backend_url.rstrip("/"),
        endpoint=args.endpoint,
        concurrency=args.concurrency,
        total_requests=args.total_requests,
        warmup=args.warmup,
        request_timeout=args.request_timeout,
        debug=args.debug,
    )


async def _one_stream_request(
    client: httpx.AsyncClient,
    prompt: str,
    debug: bool,
) -> RequestResult:
    result = RequestResult(prompt=prompt, endpoint="stream")
    body = {"message": prompt, "debug": debug}

    started_at = perf_counter()
    ttft_ms: int | None = None
    completion_tokens: int | None = None

    try:
        async with client.stream(
            "POST", "/api/chat/stream", json=body
        ) as response:
            if response.status_code != 200:
                text = (await response.aread()).decode(errors="replace")
                result.error = f"HTTP {response.status_code}: {text[:200]}"
                return result

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "content" and ttft_ms is None:
                    ttft_ms = int((perf_counter() - started_at) * 1000)
                elif event.get("type") == "metadata":
                    trace = event.get("debug_trace") or {}
                    for call in trace.get("tool_calls", []):
                        if call.get("tool_name") in {
                            "llm_generate",
                            "llm_generate_stream",
                        }:
                            summary = call.get("result_summary") or {}
                            completion_tokens = summary.get(
                                "completion_tokens", completion_tokens
                            ) or summary.get("chunks_yielded", completion_tokens)
    except httpx.HTTPError as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.ttft_ms = ttft_ms
    result.total_latency_ms = int((perf_counter() - started_at) * 1000)
    result.completion_tokens = completion_tokens
    return result


async def _one_blocking_request(
    client: httpx.AsyncClient,
    prompt: str,
    debug: bool,
) -> RequestResult:
    result = RequestResult(prompt=prompt, endpoint="chat")
    body = {"message": prompt, "debug": debug}
    started_at = perf_counter()

    try:
        response = await client.post("/api/chat", json=body)
    except httpx.HTTPError as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    total_ms = int((perf_counter() - started_at) * 1000)
    if response.status_code != 200:
        result.error = f"HTTP {response.status_code}: {response.text[:200]}"
        return result

    parsed = response.json()
    # Non-streaming endpoint: TTFT is equal to total latency (no early first byte)
    result.total_latency_ms = total_ms
    result.ttft_ms = total_ms

    trace = parsed.get("debug_trace") or {}
    for call in trace.get("tool_calls", []):
        if call.get("tool_name") == "llm_generate":
            summary = call.get("result_summary") or {}
            result.completion_tokens = summary.get("completion_tokens")
    return result


async def _run(config: BenchmarkConfig) -> list[RequestResult]:
    request_fn = (
        _one_stream_request
        if config.endpoint == "stream"
        else _one_blocking_request
    )
    prompts = [
        SAMPLE_PROMPTS[i % len(SAMPLE_PROMPTS)]
        for i in range(config.total_requests)
    ]

    sem = asyncio.Semaphore(config.concurrency)
    results: list[RequestResult] = [None] * config.total_requests  # type: ignore[list-item]

    async with httpx.AsyncClient(
        base_url=config.backend_url,
        timeout=config.request_timeout,
    ) as client:

        async def bounded(idx: int, prompt: str) -> None:
            async with sem:
                res = await request_fn(client, prompt, config.debug)
                res.counted = idx >= config.warmup
                results[idx] = res
                marker = "warmup" if not res.counted else f"#{idx + 1 - config.warmup}"
                if res.error:
                    print(f"  [{marker}] ERROR {res.error[:80]}", file=sys.stderr)
                else:
                    print(
                        f"  [{marker}] ttft={res.ttft_ms}ms  "
                        f"total={res.total_latency_ms}ms  tok={res.completion_tokens}"
                    )

        await asyncio.gather(
            *(bounded(i, p) for i, p in enumerate(prompts))
        )
    return results


def _percentile(sorted_values: list[int], pct: int) -> int | None:
    if not sorted_values:
        return None
    idx = min(int(len(sorted_values) * pct / 100), len(sorted_values) - 1)
    return sorted_values[idx]


def _print_report(config: BenchmarkConfig, results: list[RequestResult]) -> None:
    counted = [r for r in results if r.counted]
    errors = [r for r in counted if r.error]
    successes = [r for r in counted if not r.error]

    ttfts = sorted(
        r.ttft_ms for r in successes if r.ttft_ms is not None
    )
    latencies = sorted(
        r.total_latency_ms for r in successes if r.total_latency_ms is not None
    )
    total_tokens = sum(r.completion_tokens or 0 for r in successes)

    # Wall duration is the max end time minus start; approximate with sum of
    # latencies divided by concurrency to keep this dependency-free
    if latencies:
        wall_duration_s = max(latencies) / 1000 * (len(successes) / max(config.concurrency, 1))
        # Better: run-clock. We don't have it here without more bookkeeping;
        # keep the simple form and label as approx.
    else:
        wall_duration_s = 0.0

    print("\n=== IlliniGuide benchmark ===")
    print(f"endpoint:      /api/chat{'/stream' if config.endpoint == 'stream' else ''}")
    print(f"backend url:   {config.backend_url}")
    print(f"concurrency:   {config.concurrency}")
    print(
        f"total:         {len(results)} requests "
        f"({len(counted)} counted; {len(results) - len(counted)} warmup skipped)"
    )
    if len(counted) > 0:
        print(f"errors:        {len(errors)} ({len(errors) / len(counted) * 100:.1f}%)")

    if ttfts:
        print("\nTTFT (client-perceived first token):")
        print(f"  p50 = {_percentile(ttfts, 50):>6} ms")
        print(f"  p95 = {_percentile(ttfts, 95):>6} ms")
        print(f"  p99 = {_percentile(ttfts, 99):>6} ms")

    if latencies:
        print("\nTotal latency (full response):")
        print(f"  p50 = {_percentile(latencies, 50):>6} ms")
        print(f"  p95 = {_percentile(latencies, 95):>6} ms")
        print(f"  p99 = {_percentile(latencies, 99):>6} ms")

    if total_tokens > 0 and wall_duration_s > 0:
        print("\nThroughput (approximate):")
        print(f"  aggregate output: {total_tokens / wall_duration_s:.1f} tok/s")


def main() -> int:
    config = _parse_args()
    print(
        f"→ warmup {config.warmup} + {config.total_requests - config.warmup} counted "
        f"requests, concurrency={config.concurrency}, endpoint={config.endpoint}"
    )
    results = asyncio.run(_run(config))
    _print_report(config, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
