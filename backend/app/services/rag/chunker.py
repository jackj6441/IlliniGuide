"""Section-based chunker for course catalog RAG ingestion.

Each course is split into narrow, self-contained chunks so pgvector retrieval
returns focused evidence for one question at a time (a prerequisite query
does not have to compete with career-tag text embedded in the same chunk).

Every chunk is anchored with `course_id — title` at the top so the embedding
carries the course identity even when the body text is generic ("Prerequisites:
ECE 220"). The GPA context chunk is produced separately because it depends on
`gpa_stats` rows rather than the `courses` row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models import Course

_CAREER_TAG_LABELS: dict[str, str] = {
    "ai_infra": "AI infrastructure",
    "systems": "systems engineering",
    "software": "software engineering",
    "hardware": "hardware engineering",
    "ml": "machine learning",
    "security": "security",
    "networking": "networking",
    "data": "data engineering",
}

DEFAULT_CATALOG_SOURCE = "UIUC Course Catalog"
DEFAULT_GPA_SOURCE = "Wade's GPA Dataset"


@dataclass(frozen=True)
class CourseChunkDoc:
    """One RAG-ready chunk ready to be persisted into `course_chunks`."""

    course_id: str
    section_type: str
    text: str
    source_name: str
    source_url: str | None
    metadata: dict[str, Any]


def _career_phrase(tags: list[str]) -> str:
    labels = [_CAREER_TAG_LABELS.get(t, t.replace("_", " ")) for t in tags]
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} or {labels[1]}"
    return ", ".join(labels[:-1]) + f", or {labels[-1]}"


def chunk_course(
    course: Course,
    *,
    source_name: str = DEFAULT_CATALOG_SOURCE,
) -> list[CourseChunkDoc]:
    """Produce catalog-driven chunks for a single course.

    Emits up to four chunks — overview, prerequisites, credit_hours,
    career_direction — skipping any field that is None or blank so we never
    persist an empty chunk that would pollute retrieval.
    """
    course_id = course.course_id
    title = (course.title or "").strip()
    anchor = f"{course_id} — {title}".rstrip(" —") if title else course_id

    docs: list[CourseChunkDoc] = []

    def _emit(section_type: str, body: str, extra_meta: dict[str, Any] | None = None) -> None:
        text = f"{anchor}\n\n{body}"
        metadata: dict[str, Any] = {
            "course_id": course_id,
            "title": title,
            "section_type": section_type,
        }
        if extra_meta:
            metadata.update(extra_meta)
        docs.append(
            CourseChunkDoc(
                course_id=course_id,
                section_type=section_type,
                text=text,
                source_name=source_name,
                source_url=course.source_url,
                metadata=metadata,
            )
        )

    description = (course.description or "").strip()
    if description:
        _emit("overview", f"Overview: {description}")

    prerequisites = (course.prerequisites or "").strip()
    if prerequisites:
        _emit("prerequisites", f"Prerequisites: {prerequisites}")

    credit_hours = (course.credit_hours or "").strip()
    if credit_hours:
        _emit("credit_hours", f"Credit hours: {credit_hours}")

    tags = [t for t in (course.career_tags or []) if t]
    if tags:
        body = (
            "Career direction: this course is suitable for students targeting "
            f"{_career_phrase(tags)} roles."
        )
        _emit("career_direction", body, {"career_tags": list(tags)})

    return docs


def chunk_gpa_context(
    course: Course,
    avg_gpa: float | None,
    *,
    sample_size: int | None = None,
    source_name: str = DEFAULT_GPA_SOURCE,
) -> CourseChunkDoc | None:
    """Produce a single `gpa_context` chunk when GPA history exists.

    Returns None when `avg_gpa` is missing so the ingestion loop can skip
    silently for courses that have no matching `gpa_stats` rows.
    """
    if avg_gpa is None:
        return None

    course_id = course.course_id
    title = (course.title or "").strip()
    anchor = f"{course_id} — {title}".rstrip(" —") if title else course_id

    body = f"GPA context: recent average GPA is {avg_gpa:.2f} on a 4.0 scale."
    if sample_size is not None:
        body += f" Aggregated over {sample_size} term-instructor rows."

    metadata: dict[str, Any] = {
        "course_id": course_id,
        "title": title,
        "section_type": "gpa_context",
        "average_gpa": round(float(avg_gpa), 3),
    }
    if sample_size is not None:
        metadata["sample_size"] = int(sample_size)

    return CourseChunkDoc(
        course_id=course_id,
        section_type="gpa_context",
        text=f"{anchor}\n\n{body}",
        source_name=source_name,
        source_url=None,
        metadata=metadata,
    )


__all__ = [
    "CourseChunkDoc",
    "chunk_course",
    "chunk_gpa_context",
    "DEFAULT_CATALOG_SOURCE",
    "DEFAULT_GPA_SOURCE",
]
