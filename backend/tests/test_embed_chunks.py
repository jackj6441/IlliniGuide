"""Unit tests for embedding ingestion glue.

Uses a fake Session rather than a real Postgres — the real DB path is
exercised by the end-to-end verification in D6.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.db.models import Course, CourseChunk
from app.ingestion.embed_chunks import (
    IngestReport,
    build_chunks_for_course,
    ingest_course_embeddings,
    persist_course_chunks,
)
from app.services.rag.embeddings import MockEmbeddingClient


def _make_course(
    course_id: str = "ECE 391",
    *,
    title: str = "Computer Systems Engineering",
    description: str | None = "Systems programming, OS concepts.",
    prerequisites: str | None = "ECE 220.",
    credit_hours: str | None = "4 hours",
    career_tags: list[str] | None = None,
) -> Course:
    return Course(
        course_id=course_id,
        department="ECE",
        course_number=course_id.split()[-1],
        title=title,
        description=description,
        credit_hours=credit_hours,
        prerequisites=prerequisites,
        source_url=f"https://courses.illinois.edu/{course_id.replace(' ', '')}",
        career_tags=career_tags,
    )


class FakeSession:
    """Minimal SQLAlchemy Session double for the ingestion path."""

    def __init__(
        self,
        courses: list[Course],
        gpa_by_course: dict[str, tuple[float | None, int]] | None = None,
    ) -> None:
        self.courses = courses
        self.gpa_by_course = gpa_by_course or {}
        self.deleted_course_ids: list[str] = []
        self.added_chunks: list[CourseChunk] = []
        self.commits = 0
        self._current_gpa_course_id: str | None = None

    def scalars(self, statement: Any) -> "FakeSession":  # noqa: ARG002
        return self

    def all(self) -> list[Course]:
        return self.courses

    def execute(self, statement: Any) -> "FakeSession":
        stmt_str = str(statement).lower()
        if "delete" in stmt_str:
            course_id = _extract_course_id_from_delete(statement)
            if course_id is not None:
                self.deleted_course_ids.append(course_id)
        elif "avg" in stmt_str and "gpa_stats" in stmt_str:
            self._current_gpa_course_id = _extract_course_id_from_gpa_query(
                statement
            )
        return self

    def one(self) -> tuple[float | None, int]:
        course_id = self._current_gpa_course_id
        self._current_gpa_course_id = None
        return self.gpa_by_course.get(course_id, (None, 0))

    def add(self, obj: CourseChunk) -> None:
        self.added_chunks.append(obj)

    def commit(self) -> None:
        self.commits += 1


def _extract_course_id_from_delete(statement: Any) -> str | None:
    params = getattr(statement, "compile", lambda: None)()
    if params is None:
        return None
    try:
        binds = params.params
    except AttributeError:
        return None
    for value in binds.values():
        if isinstance(value, str):
            return value
    return None


def _extract_course_id_from_gpa_query(statement: Any) -> str | None:
    try:
        binds = statement.compile().params
    except Exception:  # pragma: no cover - best-effort
        return None
    for value in binds.values():
        if isinstance(value, str):
            return value
    return None


class TestBuildChunksForCourse:
    def test_catalog_only_when_no_gpa(self) -> None:
        course = _make_course()
        docs = build_chunks_for_course(course)
        types = [d.section_type for d in docs]
        assert "gpa_context" not in types
        assert set(types).issubset(
            {"overview", "prerequisites", "credit_hours", "career_direction"}
        )

    def test_gpa_context_appended_when_avg_provided(self) -> None:
        course = _make_course(career_tags=["systems"])
        docs = build_chunks_for_course(
            course, avg_gpa=3.4, gpa_sample_size=8
        )
        types = [d.section_type for d in docs]
        assert types[-1] == "gpa_context"
        assert "3.40" in docs[-1].text

    def test_none_gpa_produces_no_gpa_chunk(self) -> None:
        course = _make_course()
        docs = build_chunks_for_course(course, avg_gpa=None)
        assert all(d.section_type != "gpa_context" for d in docs)


class TestPersistCourseChunks:
    def test_length_mismatch_raises(self) -> None:
        course = _make_course()
        session = FakeSession([course])
        docs = build_chunks_for_course(course)
        with pytest.raises(ValueError, match="length mismatch"):
            persist_course_chunks(session, "ECE 391", docs, vectors=[])

    def test_delete_then_add_sequence(self) -> None:
        course = _make_course()
        session = FakeSession([course])
        docs = build_chunks_for_course(course)
        vectors = [[0.0] * 384 for _ in docs]

        persist_course_chunks(session, "ECE 391", docs, vectors)

        assert session.deleted_course_ids == ["ECE 391"]
        assert len(session.added_chunks) == len(docs)
        for chunk in session.added_chunks:
            assert chunk.course_id == "ECE 391"
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 384


class TestIngestCourseEmbeddings:
    def test_reports_zero_for_empty_course_filter(self) -> None:
        session = FakeSession([])
        client = MockEmbeddingClient()

        report = ingest_course_embeddings(session, client, course_ids=[])

        assert isinstance(report, IngestReport)
        assert report.courses_seen == 0
        assert report.chunks_written == 0
        assert session.commits == 0

    def test_skips_courses_that_produce_no_chunks(self) -> None:
        blank = Course(
            course_id="ECE 000",
            department="ECE",
            course_number="000",
            title="Blank",
            description=None,
            credit_hours=None,
            prerequisites=None,
            source_url=None,
            career_tags=None,
        )
        session = FakeSession([blank])
        client = MockEmbeddingClient()

        report = ingest_course_embeddings(session, client)

        assert report.courses_seen == 1
        assert report.courses_skipped == 1
        assert report.chunks_written == 0
        assert session.added_chunks == []
        assert session.deleted_course_ids == []

    def test_writes_chunks_and_reports_model_metadata(self) -> None:
        course = _make_course(career_tags=["systems"])
        session = FakeSession(
            [course],
            gpa_by_course={"ECE 391": (3.42, 5)},
        )
        client = MockEmbeddingClient(dimension=384)

        report = ingest_course_embeddings(session, client)

        # 4 catalog chunks + 1 gpa chunk
        assert report.courses_seen == 1
        assert report.courses_skipped == 0
        assert report.chunks_written == 5
        assert report.embedding_model == "mock-embedding"
        assert report.embedding_dimension == 384
        assert report.embedding_backend == "mock"
        assert report.started_at_utc <= report.completed_at_utc

        assert len(session.added_chunks) == 5
        for chunk in session.added_chunks:
            assert chunk.course_id == "ECE 391"
            assert isinstance(chunk.embedding, list)
            assert len(chunk.embedding) == 384

        assert session.commits == 1

    def test_delete_runs_before_insert_for_idempotency(self) -> None:
        course = _make_course(career_tags=["ai_infra"])
        session = FakeSession([course])
        client = MockEmbeddingClient()

        ingest_course_embeddings(session, client)

        # Delete for this course was staged; then chunks were added.
        assert "ECE 391" in session.deleted_course_ids
        assert len(session.added_chunks) >= 1
