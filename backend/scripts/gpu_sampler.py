"""Sample NVIDIA GPU compute and memory metrics into an auditable CSV.

This helper is intentionally independent from the load generator. Start it in
one terminal on the H200, run the benchmark in another, then keep the sampler
manifest and CSV alongside the benchmark artifact. ``--once`` is useful for a
smoke test; a real utilization claim needs a named interval and repeated
samples during the same load run.

Examples from ``backend/``::

    .venv/bin/python -m scripts.gpu_sampler --once
    .venv/bin/python -m scripts.gpu_sampler --duration-seconds 180 --interval-ms 1000 \
        --output-dir artifacts/gpu_metrics/steady-state
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


NVIDIA_QUERY = (
    "index,timestamp,utilization.gpu,memory.used,memory.total"
)
CSV_FIELDS = (
    "sampled_at_utc",
    "gpu_index",
    "nvidia_timestamp",
    "utilization_gpu_percent",
    "memory_used_mib",
    "memory_total_mib",
)


@dataclass(frozen=True)
class GPUSample:
    sampled_at_utc: str
    gpu_index: int
    nvidia_timestamp: str
    utilization_gpu_percent: float
    memory_used_mib: float
    memory_total_mib: float


def parse_nvidia_smi_output(
    text: str,
    *,
    sampled_at_utc: str,
) -> list[GPUSample]:
    """Parse ``nvidia-smi`` CSV output, ignoring headers/bad rows."""
    samples: list[GPUSample] = []
    for values in csv.reader(text.splitlines(), skipinitialspace=True):
        if len(values) < 5:
            continue
        try:
            sample = GPUSample(
                sampled_at_utc=sampled_at_utc,
                gpu_index=int(values[0]),
                nvidia_timestamp=values[1].strip(),
                utilization_gpu_percent=float(values[2]),
                memory_used_mib=float(values[3]),
                memory_total_mib=float(values[4]),
            )
        except (TypeError, ValueError):
            continue
        samples.append(sample)
    return samples


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


def _run_nvidia_smi(executable: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            executable,
            f"--query-gpu={NVIDIA_QUERY}",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _nvidia_smi_version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    line = next((line.strip() for line in result.stdout.splitlines() if line.strip()), None)
    return line


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for gpu_samples.csv and run_manifest.json.",
    )
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--duration-seconds", type=float, default=60.0)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Take exactly one sample instead of running for the duration.",
    )
    parser.add_argument("--executable", default="nvidia-smi")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.interval_ms < 1:
        print("--interval-ms must be positive", file=sys.stderr)
        return 2
    if not args.once and args.duration_seconds <= 0:
        print("--duration-seconds must be positive", file=sys.stderr)
        return 2

    run_started = _utc_now()
    output_dir = args.output_dir or Path(
        "artifacts/gpu_metrics"
    ) / f"{run_started.strftime('%Y%m%dT%H%M%SZ')}-{_git_sha()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "gpu_samples.csv"
    manifest_path = output_dir / "run_manifest.json"
    errors: list[str] = []
    sample_count = 0
    run_started_monotonic = time.monotonic()

    with samples_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        while True:
            sample_started = time.monotonic()
            sampled_at = _utc_now().isoformat()
            try:
                result = _run_nvidia_smi(args.executable)
            except FileNotFoundError:
                errors.append(f"executable not found: {args.executable}")
                break
            except subprocess.CalledProcessError as exc:
                message = (exc.stderr or str(exc)).strip()
                errors.append(f"nvidia-smi failed: {message[:200]}")
                break

            samples = parse_nvidia_smi_output(
                result.stdout,
                sampled_at_utc=sampled_at,
            )
            if not samples:
                errors.append("nvidia-smi returned no parseable GPU rows")
            for sample in samples:
                writer.writerow(asdict(sample))
            handle.flush()
            sample_count += len(samples)

            if (
                args.once
                or time.monotonic() - run_started_monotonic >= args.duration_seconds
            ):
                break
            remaining = args.interval_ms / 1000 - (time.monotonic() - sample_started)
            if remaining > 0:
                time.sleep(remaining)

    run_finished = _utc_now()
    manifest = {
        "schema_version": 1,
        "git_sha": _git_sha(),
        "command": "python -m scripts.gpu_sampler " + " ".join(argv or sys.argv[1:]),
        "executable": args.executable,
        "nvidia_smi_version": _nvidia_smi_version(args.executable),
        "query": NVIDIA_QUERY,
        "interval_ms": args.interval_ms,
        "duration_seconds": None if args.once else args.duration_seconds,
        "started_at_utc": run_started.isoformat(),
        "completed_at_utc": run_finished.isoformat(),
        "sample_count": sample_count,
        "errors": errors,
        "files": [samples_path.name, manifest_path.name],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if errors:
        print(f"GPU sampler failed; see {manifest_path}", file=sys.stderr)
        return 1
    print(f"Wrote {sample_count} GPU samples to {samples_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
