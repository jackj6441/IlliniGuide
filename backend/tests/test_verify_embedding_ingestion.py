"""Tests for the read-only embedding ingestion integrity gate."""

from __future__ import annotations

import json
from argparse import ArgumentTypeError
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from app.ingestion.embed_chunks import IngestReport
from scripts.verify_embedding_ingestion import (
    RunMetadata,
    build_run_manifest,
    validate_run_id,
    verify_embedding_integrity,
    write_manifest,
)


class _ScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class FakeVerificationSession:
    """Returns course IDs, then chunk embeddings, for two scalar queries."""

    def __init__(self, course_ids: list[str], embeddings: list[list[float] | None]) -> None:
        self._responses = [course_ids, embeddings]

    def scalars(self, statement: object) -> _ScalarResult:  # noqa: ARG002
        return _ScalarResult(self._responses.pop(0))


def test_integrity_report_accepts_non_null_minilm_vectors() -> None:
    session = FakeVerificationSession(
        ["ECE 391", "ECE 408"],
        [[0.0] * 384, [1.0] * 384, [0.5] * 384],
    )

    report = verify_embedding_integrity(session)

    assert report.is_valid is True
    assert report.course_count == 2
    assert report.chunk_count == 3
    assert report.non_null_embedding_count == 3
    assert report.wrong_dimension_count == 0
    assert report.errors == ()


def test_integrity_report_rejects_empty_corpus() -> None:
    report = verify_embedding_integrity(FakeVerificationSession([], []))

    assert report.is_valid is False
    assert "No courses found" in report.errors[0]
    assert "No course chunks found" in report.errors[1]


def test_integrity_report_rejects_null_and_wrong_dimension_vectors() -> None:
    report = verify_embedding_integrity(
        FakeVerificationSession(["ECE 391"], [None, [0.0] * 383, [0.0] * 384])
    )

    assert report.is_valid is False
    assert report.null_embedding_count == 1
    assert report.non_null_embedding_count == 2
    assert report.wrong_dimension_count == 1
    assert any("NULL embeddings" in error for error in report.errors)
    assert any("dimension 384" in error for error in report.errors)


def test_integrity_report_rejects_missing_postgres_hnsw_index() -> None:
    session = FakeVerificationSession(["ECE 391"], [[0.0] * 384])
    bind = Mock()
    bind.dialect.name = "postgresql"
    session.get_bind = Mock(return_value=bind)  # type: ignore[attr-defined]
    session.scalar = Mock(return_value=False)  # type: ignore[attr-defined]

    report = verify_embedding_integrity(session)

    assert report.hnsw_index_status == "missing"
    assert any("HNSW index" in error for error in report.errors)


def test_manifest_writer_records_safe_run_metadata(tmp_path) -> None:
    timestamp = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
    ingestion = IngestReport(
        courses_seen=2,
        courses_skipped=0,
        chunks_written=3,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        embedding_dimension=384,
        embedding_backend="sentence_transformer",
        started_at_utc=timestamp,
        completed_at_utc=timestamp,
    )
    integrity = verify_embedding_integrity(
        FakeVerificationSession(["ECE 391", "ECE 408"], [[0.0] * 384] * 3)
    )
    metadata = RunMetadata(
        run_id="20260713T120000Z-deadbee",
        git_sha="deadbeef",
        command="python -m scripts.ingest_embeddings",
        started_at_utc=timestamp,
    )

    manifest = build_run_manifest(ingestion, integrity, metadata)
    path = write_manifest(tmp_path, manifest)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert path == tmp_path / "manifest.json"
    assert saved["schema_version"] == 1
    assert saved["git_sha"] == "deadbeef"
    assert saved["embedding"]["backend"] == "sentence_transformer"
    assert saved["integrity"]["is_valid"] is True
    assert "DATABASE_URL" not in json.dumps(saved)
    with pytest.raises(FileExistsError, match="already exists"):
        write_manifest(tmp_path, manifest)


def test_run_id_cannot_escape_the_artifact_root() -> None:
    assert validate_run_id("20260713T120000Z-deadbee") == "20260713T120000Z-deadbee"
    with pytest.raises(ArgumentTypeError):
        validate_run_id("../outside-artifacts")
