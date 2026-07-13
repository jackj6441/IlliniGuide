"""Run the frozen retrieval evaluation and persist immutable raw artifacts.

Usage (after approved corpus and real embedding ingestion):
    cd backend
    EMBEDDING_BACKEND=sentence_transformer \\
    EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \\
    python -m scripts.eval_retrieval --mode semantic --top-k 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models import Course, CourseChunk
from app.services.rag.embeddings import get_embedding_client
from app.services.rag.eval import EvalReport, evaluate, format_report, load_cases


def _default_artifact_root() -> Path:
    return Path(__file__).resolve().parents[2] / "artifacts" / "retrieval_eval"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate frozen course retrieval cases")
    parser.add_argument("--mode", choices=("semantic", "keyword"), default="semantic")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--cases", type=Path, default=None, help="Path to a schema-v1 case-set JSON")
    parser.add_argument("--output-dir", type=Path, default=_default_artifact_root())
    parser.add_argument("--run-id", default=None, help="Immutable artifact directory name; defaults to UTC timestamp + git SHA")
    parser.add_argument(
        "--ingestion-manifest",
        type=Path,
        default=None,
        help="Approved corpus-ingestion manifest required for an evidence run.",
    )
    parser.add_argument(
        "--require-backend",
        default="sentence_transformer",
        help="Required embedding backend for evidence runs (default: sentence_transformer).",
    )
    parser.add_argument(
        "--allow-unlinked-corpus",
        action="store_true",
        help="Development-only: allow a run without an approved ingestion manifest.",
    )
    return parser.parse_args(argv)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def default_run_id(now: datetime | None = None, git_sha: str | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{git_sha or _git_sha()}"


def capture_corpus_snapshot(session: Any) -> dict[str, Any]:
    """Capture the persisted corpus identity needed to interpret an eval run."""
    courses = list(session.scalars(select(Course)).all())
    chunks = list(session.scalars(select(CourseChunk)).all())
    return {
        "distinct_course_count": len({course.course_id for course in courses}),
        "course_chunk_count": len(chunks),
        "source_urls": sorted({course.source_url for course in courses if course.source_url}),
    }


def describe_ingestion_manifest(path: Path | None) -> dict[str, Any] | None:
    """Record a safe link and checksum to a coordinator-approved corpus manifest."""
    if path is None:
        return None
    payload = path.read_bytes()
    parsed = json.loads(payload)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "run_id": parsed.get("run_id"),
        "total_distinct_course_count": parsed.get("total_distinct_course_count"),
        "source_urls": sorted(
            {
                entry.get("source_url")
                for entry in parsed.get("departments", [])
                if isinstance(entry, dict) and isinstance(entry.get("source_url"), str)
            }
        ),
    }


def validate_manifest_matches_corpus(
    manifest: dict[str, Any] | None, corpus_snapshot: dict[str, Any]
) -> None:
    """Reject a stale catalog manifest before attaching it to an eval artifact."""
    if manifest is None:
        return
    expected_count = manifest.get("total_distinct_course_count")
    if not isinstance(expected_count, int):
        raise ValueError("ingestion manifest is missing total_distinct_course_count")
    observed_count = corpus_snapshot.get("distinct_course_count")
    if observed_count != expected_count:
        raise ValueError(
            "ingestion manifest course count does not match the active evaluation corpus"
        )
    manifest_urls = set(manifest.get("source_urls", []))
    observed_urls = set(corpus_snapshot.get("source_urls", []))
    if not manifest_urls.issubset(observed_urls):
        raise ValueError("ingestion manifest source URLs do not match the active evaluation corpus")


def serialize_report(report: EvalReport) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return JSON-safe per-query and aggregate payloads; public CLI test seam."""
    per_query: list[dict[str, Any]] = []
    for result in report.cases:
        per_query.append(
            {
                "case_id": result.case.case_id,
                "category": result.case.category,
                "query": result.case.query,
                "expected": {
                    "acceptable_course_ids": list(result.case.expected_course_ids),
                    "section_type": result.case.expected_section_type,
                    "source_name": result.case.expected_source_name,
                    "safety": result.case.expected_safety,
                },
                "observed": {
                    "safety": result.observed_safety,
                    "top_similarity": result.top_similarity,
                    "applied_course_ids": list(result.applied_course_ids),
                    "chunks": [
                        {
                            "course_id": chunk.course_id,
                            "source_name": chunk.source_name,
                            "source_url": chunk.source_url,
                            "section_type": chunk.section_type,
                            "score": chunk.score,
                        }
                        for chunk in result.top_chunks
                    ],
                },
                "scores": {
                    "top1_hit": result.top1_hit,
                    "topk_hit": result.topk_hit,
                    "section_type_hit": result.section_type_hit,
                    "source_hit": result.source_hit,
                    "safety_hit": result.safety_hit,
                },
            }
        )
    aggregate = {
        "case_set_id": report.case_set_id,
        "retrieval_mode": report.retrieval_mode,
        "top_k": report.top_k,
        "counts": {
            "total_cases": report.total,
            "evidence_expected": report.evidence_expected,
            "top1_hits": report.top1_hits,
            "topk_hits": report.topk_hits,
            "unfiltered_evidence_expected": report.unfiltered_evidence_expected,
            "unfiltered_top1_hits": report.unfiltered_top1_hits,
            "unfiltered_topk_hits": report.unfiltered_topk_hits,
            "section_type_expected": report.section_type_expected,
            "section_type_hits": report.section_type_hits,
            "source_expected": report.source_expected,
            "source_hits": report.source_hits,
            "safety_expected": report.safety_expected,
            "safety_hits": report.safety_hits,
        },
        "rates": {
            "recall_at_1": report.top1_hit_rate,
            f"recall_at_{report.top_k}": report.topk_hit_rate,
            "unfiltered_recall_at_1": report.unfiltered_top1_hit_rate,
            f"unfiltered_recall_at_{report.top_k}": report.unfiltered_topk_hit_rate,
            "section_correctness": report.section_type_hit_rate,
            "source_citation_correctness": report.source_hit_rate,
            "unsupported_query_safety_correctness": report.safety_hit_rate,
        },
        "avg_top_similarity": report.avg_top_similarity,
    }
    return per_query, aggregate


def write_artifacts(
    report: EvalReport,
    *,
    output_dir: Path,
    run_id: str,
    command: list[str],
    case_file: Path,
    embedding_backend: str,
    embedding_model: str,
    embedding_dimension: int,
    started_at: datetime,
    finished_at: datetime,
    corpus_snapshot: dict[str, Any] | None = None,
    ingestion_manifest: dict[str, Any] | None = None,
    git_sha: str | None = None,
) -> Path:
    """Persist one immutable run directory and return it; public CLI test seam."""
    run_dir = _safe_run_directory(output_dir, run_id)
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(f"artifact run directory already exists: {run_dir}") from error
    per_query, aggregate = serialize_report(report)
    (run_dir / "per_query_results.json").write_text(json.dumps(per_query, indent=2) + "\n", encoding="utf-8")
    (run_dir / "aggregate_report.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "git_sha": git_sha or _git_sha(),
        "command": command,
        "case_set": {"path": str(case_file), "id": report.case_set_id},
        "retriever": {
            "mode": report.retrieval_mode,
            "top_k": report.top_k,
            "metadata_filter_policy": "metadata_filtered cases derive course IDs from query",
        },
        "embedding": {
            "backend": embedding_backend,
            "model": embedding_model,
            "dimension": embedding_dimension,
        },
        "corpus": corpus_snapshot or {},
        "ingestion_manifest": ingestion_manifest,
        "output_files": ["per_query_results.json", "aggregate_report.json", "run_manifest.json"],
        "limitations": [
            "This artifact measures retrieval evidence, not generated-answer correctness.",
            "Results are valid only for the recorded corpus, embedding model, retriever mode, and top-k.",
            *(
                ["No ingestion-manifest link was supplied; do not use this run as corpus-coverage evidence."]
                if ingestion_manifest is None
                else []
            ),
        ],
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return run_dir


def _safe_run_directory(output_dir: Path, run_id: str) -> Path:
    """Keep a run ID inside its artifact root; no path-like IDs are allowed."""
    candidate = Path(run_id)
    if not run_id or candidate.is_absolute() or candidate.name != run_id or run_id in {".", ".."}:
        raise ValueError("run_id must be a single directory name inside --output-dir")
    root = output_dir.resolve()
    run_dir = (root / candidate).resolve()
    if run_dir.parent != root:
        raise ValueError("run_id must resolve inside --output-dir")
    return run_dir


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.top_k <= 0:
        raise SystemExit("--top-k must be positive")
    case_set_id, cases = load_cases(args.cases) if args.cases else load_cases()
    client = get_embedding_client()
    if client.backend_name != args.require_backend:
        raise SystemExit(
            f"Embedding backend {client.backend_name!r} does not satisfy "
            f"--require-backend {args.require_backend!r}."
        )
    if args.ingestion_manifest is None and not args.allow_unlinked_corpus:
        raise SystemExit(
            "--ingestion-manifest is required for an evidence run; use "
            "--allow-unlinked-corpus only for development."
        )
    started_at = datetime.now(UTC)
    ingestion_manifest = describe_ingestion_manifest(args.ingestion_manifest)
    with SessionLocal() as session:
        corpus_snapshot = capture_corpus_snapshot(session)
        validate_manifest_matches_corpus(ingestion_manifest, corpus_snapshot)
        report = evaluate(
            session,
            client,
            cases,
            top_k=args.top_k,
            mode=args.mode,
            case_set_id=case_set_id,
        )
    finished_at = datetime.now(UTC)
    run_id = args.run_id or default_run_id(started_at)
    run_dir = write_artifacts(
        report,
        output_dir=args.output_dir,
        run_id=run_id,
        command=["python", "-m", "scripts.eval_retrieval", *([] if argv is None else argv)],
        case_file=args.cases or Path(__file__).resolve().parents[1] / "evaluation" / "retrieval_cases.v1.json",
        embedding_backend=client.backend_name,
        embedding_model=client.model_name,
        embedding_dimension=client.dimension,
        started_at=started_at,
        finished_at=finished_at,
        corpus_snapshot=corpus_snapshot,
        ingestion_manifest=ingestion_manifest,
    )
    print(format_report(report))
    print(f"Raw artifacts: {run_dir}")


if __name__ == "__main__":
    main()
