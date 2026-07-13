"""Run and verify a reproducible course-embedding ingestion.

This module intentionally keeps the validation query simple and read-only: it
loads course IDs and chunk embeddings, then validates the exact Python vector
length. That makes the gate independent of PostgreSQL's ``vector_dims`` SQL
function and gives a clear failure when a model/schema dimension drifts.

Typical live usage (from ``backend/``)::

    EMBEDDING_BACKEND=sentence_transformer \\
    EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \\
    python -m scripts.verify_embedding_ingestion

The command writes ``artifacts/embedding_ingestion/<run-id>/manifest.json``.
It never records ``DATABASE_URL`` or other environment secrets.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.init_db import HNSW_INDEX_NAME, init_database
from app.db.models import EMBEDDING_DIMENSION, Course, CourseChunk
from app.db.session import SessionLocal
from app.ingestion.embed_chunks import IngestReport, ingest_course_embeddings
from app.services.rag.embeddings import get_embedding_client


@dataclass(frozen=True)
class EmbeddingIntegrityReport:
    """Read-only evidence that stored chunk vectors match the configured schema."""

    expected_dimension: int
    course_count: int
    chunk_count: int
    non_null_embedding_count: int
    null_embedding_count: int
    wrong_dimension_count: int
    hnsw_index_status: str
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class RunMetadata:
    """Safe metadata needed to reproduce an embedding ingestion run."""

    run_id: str
    git_sha: str
    command: str
    started_at_utc: datetime


def verify_embedding_integrity(
    session: Session,
    *,
    expected_dimension: int = EMBEDDING_DIMENSION,
) -> EmbeddingIntegrityReport:
    """Check corpus, vector presence, and vector dimension without mutation."""
    course_ids = list(session.scalars(select(Course.course_id)).all())
    embeddings = list(session.scalars(select(CourseChunk.embedding)).all())

    null_embedding_count = sum(vector is None for vector in embeddings)
    non_null_embeddings = [vector for vector in embeddings if vector is not None]
    wrong_dimension_count = sum(
        len(vector) != expected_dimension for vector in non_null_embeddings
    )
    hnsw_index_status = _hnsw_index_status(session)

    errors: list[str] = []
    if not course_ids:
        errors.append("No courses found; ingest course data before embedding.")
    if not embeddings:
        errors.append("No course chunks found; embedding ingestion produced an empty corpus.")
    if null_embedding_count:
        errors.append(f"Found {null_embedding_count} NULL embeddings.")
    if wrong_dimension_count:
        errors.append(
            f"Found {wrong_dimension_count} embeddings with a dimension other "
            f"than expected dimension {expected_dimension}."
        )
    if hnsw_index_status == "missing":
        errors.append(f"Expected pgvector HNSW index {HNSW_INDEX_NAME!r} is missing.")

    return EmbeddingIntegrityReport(
        expected_dimension=expected_dimension,
        course_count=len(set(course_ids)),
        chunk_count=len(embeddings),
        non_null_embedding_count=len(non_null_embeddings),
        null_embedding_count=null_embedding_count,
        wrong_dimension_count=wrong_dimension_count,
        hnsw_index_status=hnsw_index_status,
        errors=tuple(errors),
    )


def _hnsw_index_status(session: Session) -> str:
    """Check the required HNSW index on PostgreSQL; skip non-Postgres unit doubles."""
    get_bind = getattr(session, "get_bind", None)
    if get_bind is None:
        return "not_checked"
    bind = get_bind()
    if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return "not_checked"
    exists = session.scalar(
        text("SELECT to_regclass(:index_name) IS NOT NULL"),
        {"index_name": HNSW_INDEX_NAME},
    )
    return "present" if exists else "missing"


def get_git_sha(project_root: Path | None = None) -> str:
    """Return the checked-out commit, or ``unknown`` outside a Git checkout."""
    root = project_root or Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def make_run_id(started_at_utc: datetime, git_sha: str) -> str:
    """Create a stable, sortable artifact directory name without credentials."""
    timestamp = started_at_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{git_sha[:7]}"


def validate_run_id(value: str) -> str:
    """Reject path-like values so artifacts always stay below ``artifact-root``."""
    if not value or Path(value).name != value or value in {".", ".."}:
        raise argparse.ArgumentTypeError(
            "run ID must be a single directory name under --artifact-root"
        )
    return value


def build_run_manifest(
    ingestion: IngestReport,
    integrity: EmbeddingIntegrityReport,
    metadata: RunMetadata,
) -> dict[str, Any]:
    """Build a JSON-safe manifest; do not add environment variables here."""
    return {
        "schema_version": 1,
        "run_id": metadata.run_id,
        "git_sha": metadata.git_sha,
        "command": metadata.command,
        "started_at_utc": metadata.started_at_utc.isoformat(),
        "completed_at_utc": ingestion.completed_at_utc.isoformat(),
        "embedding": {
            "backend": ingestion.embedding_backend,
            "model": ingestion.embedding_model,
            "dimension": ingestion.embedding_dimension,
        },
        "ingestion": {
            "courses_seen": ingestion.courses_seen,
            "courses_skipped": ingestion.courses_skipped,
            "chunks_written": ingestion.chunks_written,
        },
        "integrity": {**asdict(integrity), "is_valid": integrity.is_valid},
    }


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> Path:
    """Publish one immutable, non-secret manifest for this run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    if path.exists():
        raise FileExistsError(f"embedding ingestion manifest already exists: {path}")
    temporary_path = output_dir / "manifest.json.tmp"
    temporary_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("artifacts/embedding_ingestion"),
        help="Directory containing timestamped ingestion manifests.",
    )
    parser.add_argument(
        "--run-id",
        type=validate_run_id,
        help="Optional unique run identifier; defaults to UTC timestamp + Git SHA.",
    )
    parser.add_argument(
        "--expected-dimension",
        type=int,
        default=EMBEDDING_DIMENSION,
        help="Expected stored vector dimension (MiniLM-L6-v2 uses 384).",
    )
    parser.add_argument(
        "--require-backend",
        default="sentence_transformer",
        help="Required embedding backend for this evidence run (default: sentence_transformer).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Ingest once, validate the stored vectors, and return a shell status code."""
    args = _parse_args(argv)
    started_at_utc = datetime.now(UTC)
    git_sha = get_git_sha()
    run_id = args.run_id or make_run_id(started_at_utc, git_sha)
    metadata = RunMetadata(
        run_id=run_id,
        git_sha=git_sha,
        command="python -m scripts.verify_embedding_ingestion",
        started_at_utc=started_at_utc,
    )

    init_database()
    client = get_embedding_client()
    if client.backend_name != args.require_backend:
        raise SystemExit(
            f"Embedding backend {client.backend_name!r} does not satisfy "
            f"--require-backend {args.require_backend!r}."
        )
    with SessionLocal() as session:
        ingestion = ingest_course_embeddings(session, client)
        integrity = verify_embedding_integrity(
            session, expected_dimension=args.expected_dimension
        )

    manifest = build_run_manifest(ingestion, integrity, metadata)
    artifact_path = write_manifest(args.artifact_root / run_id, manifest)
    print(f"Embedding ingestion manifest: {artifact_path}")
    if integrity.is_valid:
        print(
            "Embedding integrity passed: "
            f"courses={integrity.course_count} chunks={integrity.chunk_count} "
            f"dimension={integrity.expected_dimension}"
        )
        return 0

    print("Embedding integrity failed:", file=sys.stderr)
    for error in integrity.errors:
        print(f"- {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())


__all__ = [
    "EmbeddingIntegrityReport",
    "RunMetadata",
    "build_run_manifest",
    "get_git_sha",
    "make_run_id",
    "main",
    "validate_run_id",
    "verify_embedding_integrity",
    "write_manifest",
]
