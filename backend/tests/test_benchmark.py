from scripts.benchmark import (
    BenchmarkConfig,
    RequestResult,
    _build_summary,
    _write_artifacts,
)


def test_build_summary_reports_percentiles_and_error_rate() -> None:
    config = BenchmarkConfig(
        backend_url="http://localhost:8001",
        endpoint="stream",
        concurrency=2,
        total_requests=4,
        warmup=1,
        request_timeout=30.0,
        output_dir=None,
    )
    results = [
        RequestResult(
            prompt="warmup",
            endpoint="stream",
            ttft_ms=5,
            total_latency_ms=10,
            completion_tokens=10,
            counted=False,
        ),
        RequestResult(
            prompt="ok-1",
            endpoint="stream",
            ttft_ms=10,
            total_latency_ms=100,
            completion_tokens=20,
        ),
        RequestResult(
            prompt="ok-2",
            endpoint="stream",
            ttft_ms=20,
            total_latency_ms=200,
            completion_tokens=30,
        ),
        RequestResult(
            prompt="failed",
            endpoint="stream",
            error="timeout",
        ),
    ]

    summary = _build_summary(
        config,
        results,
        started_at_utc="2026-07-14T10:00:00+00:00",
        completed_at_utc="2026-07-14T10:00:02+00:00",
    )

    assert summary["counted_requests"] == 3
    assert summary["successful_requests"] == 2
    assert summary["error_requests"] == 1
    assert summary["error_rate"] == 1 / 3
    assert summary["ttft_ms"]["p50"] == 20
    assert summary["total_latency_ms"]["p95"] == 200
    assert summary["output_tokens"] == 50
    assert summary["output_tokens_per_second"] == 25.0
    assert summary["throughput_note"] == "client completion_tokens over wall-clock run duration"


def test_write_artifacts_persists_raw_results_summary_and_manifest(tmp_path) -> None:
    config = BenchmarkConfig(
        backend_url="http://localhost:8001",
        endpoint="chat",
        concurrency=1,
        total_requests=1,
        warmup=0,
        request_timeout=30.0,
        output_dir=tmp_path,
    )
    results = [
        RequestResult(
            prompt="What is ECE 391?",
            endpoint="chat",
            ttft_ms=12,
            total_latency_ms=34,
            completion_tokens=8,
        )
    ]
    summary = _build_summary(
        config,
        results,
        started_at_utc="2026-07-14T10:00:00+00:00",
        completed_at_utc="2026-07-14T10:00:01+00:00",
    )

    output_dir = _write_artifacts(config, results, summary)

    assert output_dir == tmp_path
    assert (tmp_path / "per_request_results.json").exists()
    assert (tmp_path / "summary.json").exists()
    manifest = (tmp_path / "run_manifest.json").read_text()
    assert '"schema_version": 1' in manifest
    assert '"per_request_results.json"' in manifest
