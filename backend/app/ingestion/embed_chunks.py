"""Embed course chunks and persist them to pgvector.

This module is the glue between the pure `chunker` + `embeddings` layers and
the database. It stays idempotent by deleting all chunks for a given course
before inserting the fresh batch — safer than upsert here because the number
of chunks per course can change between runs (e.g. adding GPA context or a
career-direction chunk when new tags land).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Course, CourseChunk, GPAStat
from app.services.rag.chunker import CourseChunkDoc, chunk_course, chunk_gpa_context
from app.services.rag.embeddings import EmbeddingClient


@dataclass(frozen=True)
class IngestReport:
    courses_seen: int
    courses_skipped: int
    chunks_written: int
    embedding_model: str
    embedding_dimension: int
    embedding_backend: str
    started_at_utc: datetime
    completed_at_utc: datetime


def build_chunks_for_course(
    course: Course,
    *,
    avg_gpa: float | None = None,
    gpa_sample_size: int | None = None,
) -> list[CourseChunkDoc]:
    """Combine catalog and GPA chunks for a single course."""
    docs = list(chunk_course(course))
    gpa_doc = chunk_gpa_context(
        course, avg_gpa=avg_gpa, sample_size=gpa_sample_size
    )
    if gpa_doc is not None:
        docs.append(gpa_doc)
    return docs


def fetch_gpa_summary(
    session: Session, course_id: str
) -> tuple[float | None, int]:
    """Aggregate GPA across all instructor/term rows for one course."""
    row = session.execute(
        select(func.avg(GPAStat.average_gpa), func.count(GPAStat.id)).where(
            GPAStat.course_id == course_id,
            GPAStat.average_gpa.is_not(None),
        )
    ).one()
    avg, count = row
    if avg is None:
        return None, 0
    return float(avg), int(count)


def persist_course_chunks(
    session: Session,
    course_id: str,
    docs: list[CourseChunkDoc],
    vectors: list[list[float]],
) -> None:
    """Replace all chunks for a course atomically (delete-then-insert).

    The caller commits — this function only stages the write so multiple
    course ingests can share one commit and roll back cleanly on failure.
    """
    if len(docs) != len(vectors):
        raise ValueError(
            f"docs/vectors length mismatch: {len(docs)} vs {len(vectors)}"
        )

    session.execute(
        delete(CourseChunk).where(CourseChunk.course_id == course_id)
    )
    for doc, vec in zip(docs, vectors):
        session.add(
            CourseChunk(
                course_id=doc.course_id,
                source_name=doc.source_name,
                source_url=doc.source_url,
                section_type=doc.section_type,
                chunk_text=doc.text,
                metadata_=doc.metadata,
                embedding=vec,
            )
        )


def ingest_course_embeddings(
    session: Session,
    embedding_client: EmbeddingClient,
    *,
    course_ids: Iterable[str] | None = None,
) -> IngestReport:
    """Chunk, embed, and persist chunks for the given (or all) courses.

    When `course_ids` is None the full `courses` table is processed. Courses
    that produce zero chunks (all catalog fields blank, no GPA history) are
    counted as skipped and their existing chunks are left untouched.
    """
    started_at_utc = datetime.now(UTC)
    statement = select(Course)
    if course_ids is not None:
        wanted = list(course_ids)
        if not wanted:
            completed_at_utc = datetime.now(UTC)
            return IngestReport(
                courses_seen=0,
                courses_skipped=0,
                chunks_written=0,
                embedding_model=embedding_client.model_name,
                embedding_dimension=embedding_client.dimension,
                embedding_backend=embedding_client.backend_name,
                started_at_utc=started_at_utc,
                completed_at_utc=completed_at_utc,
            )
        statement = statement.where(Course.course_id.in_(wanted))

    courses = list(session.scalars(statement).all())

    courses_seen = 0
    courses_skipped = 0
    chunks_written = 0

    for course in courses:
        courses_seen += 1
        avg_gpa, sample_size = fetch_gpa_summary(session, course.course_id)
        docs = build_chunks_for_course(
            course,
            avg_gpa=avg_gpa,
            gpa_sample_size=sample_size or None,
        )
        if not docs:
            courses_skipped += 1
            continue

        vectors = embedding_client.embed([d.text for d in docs])
        persist_course_chunks(session, course.course_id, docs, vectors)
        chunks_written += len(docs)

    session.commit()

    completed_at_utc = datetime.now(UTC)
    return IngestReport(
        courses_seen=courses_seen,
        courses_skipped=courses_skipped,
        chunks_written=chunks_written,
        embedding_model=embedding_client.model_name,
        embedding_dimension=embedding_client.dimension,
        embedding_backend=embedding_client.backend_name,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
    )


__all__ = [
    "IngestReport",
    "build_chunks_for_course",
    "fetch_gpa_summary",
    "persist_course_chunks",
    "ingest_course_embeddings",
]
