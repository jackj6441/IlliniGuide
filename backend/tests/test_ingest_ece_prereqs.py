import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.ingestion.ece_prereqs import (
    ECECourseRecord,
    ingest_ece_prereqs_html,
    normalize_whitespace,
    parse_ece_course_records,
)
from app.ingestion.course_catalog import CourseIngestionResult, write_ingestion_manifest
from app.ingestion.cs_catalog import CSCourseRecord, ingest_cs_courses_html, parse_cs_course_records
from scripts.ingest_course_catalogs import ingest_course_catalogs_html


HTML_FIXTURE = """
<table>
<tbody>
<tr>
  <td class="rubric"><a>ECE 385</a></td>
  <td class="title"><a>Digital Systems Laboratory</a></td>
  <td class="prereqs">Credit in <a>ECE 110</a> <br />Credit in <a>ECE 220</a></td>
</tr>
<tr>
  <td class="rubric"><a>ECE 391</a></td>
  <td class="title"><a>Computer Systems Engineering</a></td>
  <td class="prereqs">Credit in <a>CS 233</a> or <a>ECE 220</a></td>
</tr>
<tr>
  <td class="rubric"><a>CS 225</a></td>
  <td class="title"><a>Data Structures</a></td>
  <td class="prereqs">Ignored</td>
</tr>
<tr>
  <td class="rubric"><a>ECE 385</a></td>
  <td class="title"><a>Digital Systems Laboratory</a></td>
  <td class="prereqs">Duplicate tab row</td>
</tr>
</tbody>
</table>
"""


def test_parse_ece_course_records_extracts_table_rows() -> None:
    records = parse_ece_course_records(HTML_FIXTURE)

    assert records[:2] == [
        ECECourseRecord(
            course_id="ECE 385",
            department="ECE",
            course_number="385",
            title="Digital Systems Laboratory",
            prerequisites="Credit in ECE 110 Credit in ECE 220",
        ),
        ECECourseRecord(
            course_id="ECE 391",
            department="ECE",
            course_number="391",
            title="Computer Systems Engineering",
            prerequisites="Credit in CS 233 or ECE 220",
        ),
    ]
    assert all(record.department == "ECE" for record in records)


def test_ingest_ece_prereqs_html_deduplicates_course_ids_per_run() -> None:
    session = Mock()
    with patch("app.ingestion.ece_prereqs.upsert_course") as upsert_course:
        result = ingest_ece_prereqs_html(
            session,
            HTML_FIXTURE,
            limit=20,
            source_url="https://example.com/ece-courses",
        )

    assert result.rows_ingested == 2
    assert upsert_course.call_count == 2
    assert upsert_course.call_args_list[0].args[1].course_id == "ECE 385"
    assert upsert_course.call_args_list[1].args[1].course_id == "ECE 391"
    session.commit.assert_called_once()
    assert result.duplicate_count == 1


def test_normalize_whitespace_unescapes_and_collapses_spaces() -> None:
    assert normalize_whitespace("Credit&nbsp;in  ECE 110\nCredit in ECE 220") == (
        "Credit in ECE 110 Credit in ECE 220"
    )


def test_ingest_ece_prereqs_skips_missing_or_malformed_identity() -> None:
    session = Mock()
    records = [
        ECECourseRecord("ECE 385", "ECE", "385", "Digital Systems", None),
        ECECourseRecord("ECE nope", "ECE", "nope", "Broken", None),
        ECECourseRecord("ECE 391", "CS", "391", "Wrong department", None),
        ECECourseRecord("ECE 411", "ECE", "411", "", None),
    ]
    with patch("app.ingestion.ece_prereqs.parse_ece_course_records", return_value=records), patch(
        "app.ingestion.ece_prereqs.upsert_course", return_value="inserted"
    ) as upsert_course:
        result = ingest_ece_prereqs_html(session, "<html></html>")

    assert result.inserted_count == 1
    assert result.skipped_count == 3
    assert upsert_course.call_count == 1


def test_ingest_ece_prereqs_rejects_missing_source_url() -> None:
    with pytest.raises(ValueError, match="source_url"):
        ingest_ece_prereqs_html(Mock(), HTML_FIXTURE, source_url=" ")


def test_parse_cs_course_records_uses_saved_catalog_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "cs_course_catalog.html"
    records = parse_cs_course_records(fixture_path.read_text(encoding="utf-8"))

    assert records[:2] == [
        CSCourseRecord(
            course_id="CS 124",
            department="CS",
            course_number="124",
            title="Introduction to Computer Science I",
            prerequisites="Credit or concurrent registration in MATH 220 or MATH 221.",
        ),
        CSCourseRecord(
            course_id="CS 225",
            department="CS",
            course_number="225",
            title="Data Structures",
            prerequisites="CS 124.",
        ),
    ]
    assert records[2].course_id == "CS 233"
    assert records[2].prerequisites is None
    assert records[-1].prerequisites == "malformed ["


def test_parse_cs_course_records_supports_current_official_catalog_markup() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "cs_course_catalog_current_markup.html"
    html = fixture_path.read_text(encoding="utf-8")

    assert parse_cs_course_records(html) == [
        CSCourseRecord(
            course_id="CS 100",
            department="CS",
            course_number="100",
            title="Computer Science Orientation",
            prerequisites="None.",
        ),
        CSCourseRecord(
            course_id="CS 124",
            department="CS",
            course_number="124",
            title="Introduction to Computer Science I",
            prerequisites="Credit or concurrent registration in MATH 220.",
        ),
    ]


def test_ingest_cs_courses_is_idempotent_at_public_api_seam() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "cs_course_catalog.html"
    html = fixture_path.read_text(encoding="utf-8")
    session = Mock()
    with patch(
        "app.ingestion.cs_catalog.upsert_course", side_effect=["inserted", "inserted", "inserted"]
    ):
        first = ingest_cs_courses_html(session, html)
    with patch(
        "app.ingestion.cs_catalog.upsert_course", side_effect=["updated", "updated", "updated"]
    ):
        second = ingest_cs_courses_html(session, html)

    assert first.inserted_count == 3
    assert second.updated_count == 3
    assert first.duplicate_count == second.duplicate_count == 1
    assert session.commit.call_count == 2


def test_write_ingestion_manifest_records_per_department_counts(tmp_path) -> None:
    session = Mock()
    with patch("app.ingestion.ece_prereqs.upsert_course", return_value="inserted"):
        result = ingest_ece_prereqs_html(session, HTML_FIXTURE, source_url="https://example.com/ece")

    manifest = write_ingestion_manifest(
        tmp_path,
        [result],
        fetched_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        run_id="test-run",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert payload["fetched_at"] == "2026-07-13T00:00:00+00:00"
    assert payload["departments"] == [
        {
            "department": "ECE",
            "duplicate_count": 1,
            "inserted_count": 2,
            "parsed_count": 3,
            "skipped_count": 0,
            "source_url": "https://example.com/ece",
            "updated_count": 0,
        }
    ]


@pytest.mark.parametrize("run_id", ["../outside", "nested/run", "/tmp/outside", ".", ".."])
def test_write_ingestion_manifest_rejects_path_like_run_ids(tmp_path, run_id: str) -> None:
    result = CourseIngestionResult(
        department="ECE",
        source_url="https://example.com/ece",
        parsed_count=1,
        inserted_count=1,
        updated_count=0,
        skipped_count=0,
        duplicate_count=0,
    )

    with pytest.raises(ValueError, match="run_id"):
        write_ingestion_manifest(
            tmp_path,
            [result],
            fetched_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
            run_id=run_id,
        )


def test_combined_ingestion_reports_distinct_course_count_in_one_manifest(tmp_path) -> None:
    session = Mock()
    ece_result = CourseIngestionResult(
        department="ECE",
        source_url="https://example.com/ece",
        parsed_count=80,
        inserted_count=80,
        updated_count=0,
        skipped_count=0,
        duplicate_count=0,
    )
    cs_result = CourseIngestionResult(
        department="CS",
        source_url="https://example.com/cs",
        parsed_count=75,
        inserted_count=75,
        updated_count=0,
        skipped_count=0,
        duplicate_count=0,
    )
    session.scalar.return_value = 155
    with patch("scripts.ingest_course_catalogs.ingest_ece_prereqs_html", return_value=ece_result), patch(
        "scripts.ingest_course_catalogs.ingest_cs_courses_html", return_value=cs_result
    ):
        results = ingest_course_catalogs_html(session, "ece", "cs")

    manifest = write_ingestion_manifest(
        tmp_path,
        results[:2],
        fetched_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        run_id="combined-run",
        total_distinct_course_count=results[2],
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert results[2] == 155
    session.flush.assert_called_once()
    called_methods = [method[0] for method in session.method_calls]
    assert called_methods.index("flush") < called_methods.index("scalar")
    assert [entry["department"] for entry in payload["departments"]] == ["ECE", "CS"]
    assert payload["total_distinct_course_count"] == 155


def test_combined_ingestion_rolls_back_when_second_source_fails() -> None:
    session = Mock()
    ece_result = CourseIngestionResult(
        department="ECE",
        source_url="https://example.com/ece",
        parsed_count=1,
        inserted_count=1,
        updated_count=0,
        skipped_count=0,
        duplicate_count=0,
    )
    with patch("scripts.ingest_course_catalogs.ingest_ece_prereqs_html", return_value=ece_result) as ingest_ece, patch(
        "scripts.ingest_course_catalogs.ingest_cs_courses_html", side_effect=RuntimeError("CS source failed")
    ) as ingest_cs:
        with pytest.raises(RuntimeError, match="CS source failed"):
            ingest_course_catalogs_html(session, "ece", "cs")

    assert ingest_ece.call_args.kwargs["commit"] is False
    assert ingest_cs.call_args.kwargs["commit"] is False
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_combined_ingestion_rolls_back_when_first_source_fails() -> None:
    session = Mock()
    with patch(
        "scripts.ingest_course_catalogs.ingest_ece_prereqs_html", side_effect=RuntimeError("ECE source failed")
    ) as ingest_ece, patch("scripts.ingest_course_catalogs.ingest_cs_courses_html") as ingest_cs:
        with pytest.raises(RuntimeError, match="ECE source failed"):
            ingest_course_catalogs_html(session, "ece", "cs")

    assert ingest_ece.call_args.kwargs["commit"] is False
    ingest_cs.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()
