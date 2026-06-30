from unittest.mock import Mock, patch

from app.ingestion.ece_prereqs import (
    ECECourseRecord,
    ingest_ece_prereqs_html,
    normalize_whitespace,
    parse_ece_course_records,
)


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


def test_normalize_whitespace_unescapes_and_collapses_spaces() -> None:
    assert normalize_whitespace("Credit&nbsp;in  ECE 110\nCredit in ECE 220") == (
        "Credit in ECE 110 Credit in ECE 220"
    )
