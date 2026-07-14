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
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
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
    output_dir: Path | None = None


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
        "--output-dir",
        type=Path,
        help="Write per-request JSON, summary JSON, and a run manifest here.",
    )
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
        output_dir=args.output_dir,
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


def _build_summary(
    config: BenchmarkConfig,
    results: list[RequestResult],
    *,
    started_at_utc: str,
    completed_at_utc: str,
) -> dict:
    counted = [r for r in results if r.counted]
    errors = [r for r in counted if r.error]
    successes = [r for r in counted if not r.error]
    ttfts = sorted(r.ttft_ms for r in successes if r.ttft_ms is not None)
    latencies = sorted(
        r.total_latency_ms for r in successes if r.total_latency_ms is not None
    )
    total_tokens = sum(r.completion_tokens or 0 for r in successes)
    started = datetime.fromisoformat(started_at_utc)
    completed = datetime.fromisoformat(completed_at_utc)
    wall_duration_seconds = max(0.0, (completed - started).total_seconds())

    return {
        "total_requests": len(results),
        "counted_requests": len(counted),
        "warmup_requests": len(results) - len(counted),
        "successful_requests": len(successes),
        "error_requests": len(errors),
        "error_rate": len(errors) / len(counted) if counted else None,
        "ttft_ms": {
            "p50": _percentile(ttfts, 50),
            "p95": _percentile(ttfts, 95),
            "p99": _percentile(ttfts, 99),
            "sample_count": len(ttfts),
        },
        "total_latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "sample_count": len(latencies),
        },
        "output_tokens": total_tokens,
        "wall_duration_seconds": wall_duration_seconds,
        "output_tokens_per_second": (
            total_tokens / wall_duration_seconds
            if total_tokens and wall_duration_seconds > 0
            else None
        ),
        "throughput_note": (
            "client completion_tokens over wall-clock run duration"
            if total_tokens
            else "no completion token counts reported"
        ),
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "endpoint": f"/api/chat{'/stream' if config.endpoint == 'stream' else ''}",
        "concurrency": config.concurrency,
    }


def _print_report(
    config: BenchmarkConfig,
    results: list[RequestResult],
    summary: dict,
) -> None:
    counted = [r for r in results if r.counted]
    errors = [r for r in counted if r.error]

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

    if summary["ttft_ms"]["sample_count"]:
        print("\nTTFT (client-perceived first token):")
        print(f"  p50 = {summary['ttft_ms']['p50']:>6} ms")
        print(f"  p95 = {summary['ttft_ms']['p95']:>6} ms")
        print(f"  p99 = {summary['ttft_ms']['p99']:>6} ms")

    if summary["total_latency_ms"]["sample_count"]:
        print("\nTotal latency (full response):")
        print(f"  p50 = {summary['total_latency_ms']['p50']:>6} ms")
        print(f"  p95 = {summary['total_latency_ms']['p95']:>6} ms")
        print(f"  p99 = {summary['total_latency_ms']['p99']:>6} ms")

    if summary["output_tokens_per_second"] is not None:
        print("\nThroughput (client-reported):")
        print(f"  aggregate output: {summary['output_tokens_per_second']:.1f} tok/s")


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _write_artifacts(
    config: BenchmarkConfig,
    results: list[RequestResult],
    summary: dict,
) -> Path | None:
    if config.output_dir is None:
        return None
    config.output_dir.mkdir(parents=True, exist_ok=True)
    per_request_path = config.output_dir / "per_request_results.json"
    summary_path = config.output_dir / "summary.json"
    manifest_path = config.output_dir / "run_manifest.json"
    per_request_path.write_text(
        json.dumps([asdict(result) for result in results], indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "git_sha": _git_sha(),
        "command": "python -m scripts.benchmark " + " ".join(sys.argv[1:]),
        "backend_url": config.backend_url,
        "endpoint": config.endpoint,
        "concurrency": config.concurrency,
        "total_requests": config.total_requests,
        "warmup": config.warmup,
        "request_timeout_seconds": config.request_timeout,
        "debug": config.debug,
        "files": [
            per_request_path.name,
            summary_path.name,
            manifest_path.name,
        ],
        "summary": summary,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return config.output_dir


def main() -> int:
    config = _parse_args()
    print(
        f"→ warmup {config.warmup} + {config.total_requests - config.warmup} counted "
        f"requests, concurrency={config.concurrency}, endpoint={config.endpoint}"
    )
    started_at_utc = datetime.now(UTC).isoformat()
    results = asyncio.run(_run(config))
    completed_at_utc = datetime.now(UTC).isoformat()
    summary = _build_summary(
        config,
        results,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
    )
    _print_report(config, results, summary)
    artifact_dir = _write_artifacts(config, results, summary)
    if artifact_dir:
        print(f"Artifacts: {artifact_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
