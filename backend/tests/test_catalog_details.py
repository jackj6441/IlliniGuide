from pathlib import Path
from unittest.mock import Mock, patch

from app.ingestion.catalog_details import (
    CatalogCourseRecord,
    ingest_catalog_details_html,
    parse_catalog_detail_records,
)
from app.db.models import Course
from app.ingestion.course_catalog import CourseIngestionResult, upsert_source_course
from scripts.enrich_catalog_details import enrich_catalog_details_html


def test_parse_catalog_detail_records_extracts_overview_credit_and_prerequisite() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "ece_catalog_details.html"

    records = parse_catalog_detail_records(
        fixture_path.read_text(encoding="utf-8"), department="ECE"
    )

    assert records == [
        CatalogCourseRecord(
            course_id="ECE 408",
            department="ECE",
            course_number="408",
            title="Applied Parallel Programming",
            prerequisites="ECE 220 or CS 225.",
            description="Introduction to parallel programming models, GPU computing, and performance optimization.",
            credit_hours="4 Hours",
        ),
        CatalogCourseRecord(
            course_id="ECE 411",
            department="ECE",
            course_number="411",
            title="Computer Organization and Design",
            prerequisites=None,
            description="Computer organization, instruction sets, memory hierarchy, and processor design.",
            credit_hours="4 Hours",
        ),
    ]


def test_ingest_catalog_details_uses_source_tagged_upsert() -> None:
    session = Mock()
    record = CatalogCourseRecord(
        course_id="ECE 408",
        department="ECE",
        course_number="408",
        title="Applied Parallel Programming",
        prerequisites=None,
        description="GPU computing.",
        credit_hours="4 Hours",
    )
    with patch(
        "app.ingestion.catalog_details.parse_catalog_detail_records", return_value=[record]
    ), patch("app.ingestion.catalog_details.upsert_catalog_detail", return_value="updated") as upsert:
        result = ingest_catalog_details_html(
            session,
            "<html></html>",
            department="ECE",
            source_url="https://catalog.example/ece",
        )

    assert result.updated_count == 1
    assert upsert.call_args.args[1] == record
    assert session.commit.called


def test_catalog_detail_upsert_enriches_fields_without_erasing_existing_prerequisite() -> None:
    course = Course(
        course_id="ECE 408",
        department="ECE",
        course_number="408",
        title="Applied Parallel Programming",
        prerequisites="ECE 220",
        description=None,
        credit_hours=None,
        source_url="https://ece.example",
        career_tags=None,
    )
    record = CatalogCourseRecord(
        course_id="ECE 408",
        department="ECE",
        course_number="408",
        title="Applied Parallel Programming",
        prerequisites=None,
        description="GPU computing and parallel programming.",
        credit_hours="4 Hours",
    )
    session = Mock()
    session.scalar.return_value = course

    action = upsert_source_course(session, record, source_url="https://catalog.example/ece")

    assert action == "updated"
    assert course.description == "GPU computing and parallel programming."
    assert course.credit_hours == "4 Hours"
    assert course.prerequisites == "ECE 220"


def test_combined_catalog_detail_enrichment_flushes_before_count() -> None:
    session = Mock()
    ece_result = CourseIngestionResult("ECE", "https://catalog.example/ece", 1, 0, 1, 0, 0)
    cs_result = CourseIngestionResult("CS", "https://catalog.example/cs", 1, 0, 1, 0, 0)
    session.scalar.return_value = 360
    with patch("scripts.enrich_catalog_details.ingest_catalog_details_html", side_effect=[ece_result, cs_result]):
        results = enrich_catalog_details_html(session, "ece", "cs")

    assert results[2] == 360
    session.flush.assert_called_once()
    session.commit.assert_called_once()
