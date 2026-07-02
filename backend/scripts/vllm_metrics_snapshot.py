"""Snapshot key vLLM metrics and print a human-readable summary.

Usage:
    .venv/bin/python -m scripts.vllm_metrics_snapshot
    .venv/bin/python -m scripts.vllm_metrics_snapshot --base-url http://localhost:8000

vLLM exposes Prometheus text-format metrics at ``/metrics``. This script
parses only the handful we actually care about and labels them with what
they mean, so the raw text-format output does not have to be understood
before you can read what the server is doing. The metric names come from
vLLM upstream and may shift between vLLM releases; the parser tolerates
missing metrics rather than crashing.
"""

import argparse
import os
import re
import sys

import httpx


# Metric name -> (display label, unit)
KEY_METRICS: dict[str, tuple[str, str]] = {
    "vllm:num_requests_running": ("requests running", ""),
    "vllm:num_requests_waiting": ("requests waiting (queued)", ""),
    "vllm:gpu_cache_usage_perc": ("GPU KV cache usage", "%"),
    "vllm:cpu_cache_usage_perc": ("CPU KV cache usage", "%"),
    "vllm:prompt_tokens_total": ("prefill tokens (total)", "tokens"),
    "vllm:generation_tokens_total": ("decode tokens (total)", "tokens"),
    "vllm:avg_prompt_throughput_toks_per_s": (
        "prompt throughput",
        "tok/s",
    ),
    "vllm:avg_generation_throughput_toks_per_s": (
        "generation throughput",
        "tok/s",
    ),
    "vllm:time_to_first_token_seconds_sum": (
        "TTFT (cumulative sum)",
        "seconds",
    ),
    "vllm:time_to_first_token_seconds_count": (
        "TTFT (sample count)",
        "requests",
    ),
    "vllm:time_per_output_token_seconds_sum": (
        "time per output token (cumulative sum)",
        "seconds",
    ),
}


_METRIC_LINE = re.compile(
    r"^(?P<name>[A-Za-z_:][A-Za-z0-9_:]*)"
    r"(?:\{[^}]*\})?"                     # optional labels
    r"\s+(?P<value>[-+eE0-9.]+|NaN)$"
)


def _parse_metrics_text(text: str) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _METRIC_LINE.match(line.strip())
        if not match:
            continue
        name = match.group("name")
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        # If a metric has multiple label sets we sum them for a total
        parsed[name] = parsed.get(name, 0.0) + value
    return parsed


def _detect_model(text: str) -> str | None:
    # vLLM emits e.g. `vllm:e2e_request_latency_seconds_bucket{model_name="..."}`
    match = re.search(r'model_name="([^"]+)"', text)
    return match.group(1) if match else None


def _format_value(name: str, value: float, unit: str) -> str:
    if name.endswith("_perc"):
        return f"{value:6.1f}%"
    if unit == "%":
        return f"{value:6.1f}%"
    if unit == "seconds":
        return f"{value:8.4f} s"
    if unit == "tok/s":
        return f"{value:8.2f} tok/s"
    if unit == "tokens":
        return f"{int(value):>8d} tokens"
    return f"{value:8.2f} {unit}".rstrip()


def _fetch(base_url: str, timeout_seconds: float) -> str:
    with httpx.Client(base_url=base_url, timeout=timeout_seconds) as client:
        response = client.get("/metrics")
        response.raise_for_status()
        return response.text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("VLLM_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        text = _fetch(args.base_url, args.timeout)
    except httpx.HTTPError as exc:
        print(
            f"FAIL — could not reach {args.base_url}/metrics: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    metrics = _parse_metrics_text(text)
    model = _detect_model(text)

    print(f"=== vLLM metrics snapshot @ {args.base_url}/metrics ===")
    print(f"model:                        {model or '(unknown)'}")
    print()

    for metric_name, (label, unit) in KEY_METRICS.items():
        if metric_name not in metrics:
            print(f"  {label:32s} (not reported by this vLLM build)")
            continue
        formatted = _format_value(metric_name, metrics[metric_name], unit)
        print(f"  {label:32s} {formatted}")

    # Derived metric: mean TTFT if both sum and count are present
    ttft_sum = metrics.get("vllm:time_to_first_token_seconds_sum")
    ttft_count = metrics.get("vllm:time_to_first_token_seconds_count")
    if ttft_sum is not None and ttft_count and ttft_count > 0:
        print()
        print(
            f"  {'avg time to first token':32s} "
            f"{ttft_sum / ttft_count * 1000:8.1f} ms  "
            f"(over {int(ttft_count)} requests)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
