"""Unit tests for the section-based course chunker."""

from __future__ import annotations

import pytest

from app.db.models import Course
from app.services.rag.chunker import (
    CourseChunkDoc,
    chunk_course,
    chunk_gpa_context,
)


def _make_course(
    *,
    course_id: str = "ECE 391",
    title: str = "Computer Systems Engineering",
    description: str | None = None,
    prerequisites: str | None = None,
    credit_hours: str | None = None,
    career_tags: list[str] | None = None,
    source_url: str | None = "https://courses.illinois.edu/ece391",
) -> Course:
    return Course(
        course_id=course_id,
        department="ECE",
        course_number="391",
        title=title,
        description=description,
        credit_hours=credit_hours,
        prerequisites=prerequisites,
        source_url=source_url,
        career_tags=career_tags,
    )


def test_minimal_course_produces_no_chunks() -> None:
    course = _make_course()
    assert chunk_course(course) == []


def test_description_produces_overview_chunk() -> None:
    course = _make_course(description="Systems programming, OS concepts, C, concurrency.")
    docs = chunk_course(course)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.section_type == "overview"
    assert doc.course_id == "ECE 391"
    assert doc.text.startswith("ECE 391 — Computer Systems Engineering")
    assert "Overview:" in doc.text
    assert "Systems programming" in doc.text
    assert doc.source_name == "UIUC Course Catalog"
    assert doc.source_url == "https://courses.illinois.edu/ece391"
    assert doc.metadata["course_id"] == "ECE 391"
    assert doc.metadata["section_type"] == "overview"


def test_prerequisites_and_credit_hours_produce_separate_chunks() -> None:
    course = _make_course(
        prerequisites="ECE 220 with a grade of C or better.",
        credit_hours="4 hours",
    )
    docs = chunk_course(course)
    types = [d.section_type for d in docs]
    assert types == ["prerequisites", "credit_hours"]
    assert "Prerequisites: ECE 220" in docs[0].text
    assert "Credit hours: 4 hours" in docs[1].text


def test_career_tags_single_produces_singular_phrase() -> None:
    course = _make_course(career_tags=["ai_infra"])
    docs = chunk_course(course)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.section_type == "career_direction"
    assert "AI infrastructure roles" in doc.text
    assert doc.metadata["career_tags"] == ["ai_infra"]


def test_gpu_programming_tag_uses_explicit_cuda_label() -> None:
    course = _make_course(career_tags=["gpu_programming"])
    docs = chunk_course(course)
    assert "GPU programming and CUDA roles" in docs[0].text


def test_career_tags_two_uses_or_conjunction() -> None:
    course = _make_course(career_tags=["ai_infra", "systems"])
    docs = chunk_course(course)
    assert "AI infrastructure or systems engineering roles" in docs[0].text


def test_career_tags_three_plus_uses_serial_comma() -> None:
    course = _make_course(career_tags=["ai_infra", "systems", "software"])
    docs = chunk_course(course)
    assert (
        "AI infrastructure, systems engineering, or software engineering roles"
        in docs[0].text
    )


def test_unknown_career_tag_falls_back_to_readable_form() -> None:
    course = _make_course(career_tags=["quantum_computing"])
    docs = chunk_course(course)
    assert "quantum computing roles" in docs[0].text


def test_full_course_emits_four_chunks_in_order() -> None:
    course = _make_course(
        description="Systems programming and OS concepts.",
        prerequisites="ECE 220.",
        credit_hours="4 hours",
        career_tags=["systems"],
    )
    docs = chunk_course(course)
    assert [d.section_type for d in docs] == [
        "overview",
        "prerequisites",
        "credit_hours",
        "career_direction",
    ]
    for d in docs:
        assert d.text.startswith("ECE 391 — Computer Systems Engineering")
        assert d.course_id == "ECE 391"
        assert d.metadata["title"] == "Computer Systems Engineering"


def test_blank_string_fields_are_treated_as_missing() -> None:
    course = _make_course(description="   ", prerequisites="\n", credit_hours="")
    assert chunk_course(course) == []


def test_anchor_falls_back_to_course_id_when_title_missing() -> None:
    course = _make_course(title="", description="Some overview.")
    docs = chunk_course(course)
    assert docs[0].text.startswith("ECE 391\n\n")


def test_gpa_context_none_returns_none() -> None:
    course = _make_course()
    assert chunk_gpa_context(course, avg_gpa=None) is None


def test_gpa_context_with_sample_size_includes_both_facts() -> None:
    course = _make_course()
    doc = chunk_gpa_context(course, avg_gpa=3.472, sample_size=12)
    assert isinstance(doc, CourseChunkDoc)
    assert doc.section_type == "gpa_context"
    assert doc.source_name == "Wade's GPA Dataset"
    assert "average GPA is 3.47" in doc.text
    assert "12 term-instructor rows" in doc.text
    assert doc.metadata["average_gpa"] == pytest.approx(3.472)
    assert doc.metadata["sample_size"] == 12


def test_gpa_context_without_sample_size_omits_sample_sentence() -> None:
    course = _make_course()
    doc = chunk_gpa_context(course, avg_gpa=3.1)
    assert doc is not None
    assert "term-instructor rows" not in doc.text
    assert "sample_size" not in doc.metadata
