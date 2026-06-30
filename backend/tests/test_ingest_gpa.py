from unittest.mock import Mock, patch

from app.ingestion.gpa import (
    build_grade_distribution,
    ingest_waf_gpa_csv,
    parse_course,
)


CSV_FIXTURE = """instructor,instructor_first_name,course,course_name,num_excellence_awards,num_outstanding_awards,uiuc_award,national_award,rmp_num_reviews,rmp_rating,A+,A,A-,B+,B,B-,C+,C,C-,D+,D,D-,F,term,num_sections,gened,num_semesters,num_students,avg_gpa,total_faculty_awards,teaching_next_semester,instructor_first_initial,dropped_sections
Doe,Jane,CS 225: Data Structures,Data Structures,1.0,0.0,[],[],2.0,4.2,0.1,0.2,0.1,0.1,0.1,0.05,0.05,0.05,0.01,0.01,0.01,0.0,0.02,"['fa2025']",3.0,,1,100.0,3.45,0,True,J,
Smith,Alex,ECE 408: Applied Parallel Programming,Applied Parallel Programming,0.0,1.0,[],[],0.0,,0.2,0.3,0.1,0.1,0.1,0.05,0.05,0.02,0.01,0.0,0.0,0.0,0.01,"['sp2026']",2.0,,1,80.0,3.62,0,False,A,
Other,Pat,AAS 100: Intro Asian American Studies,Intro Asian American Studies,0.0,0.0,[],[],0.0,,0.2,0.3,0.1,0.1,0.1,0.05,0.05,0.02,0.01,0.0,0.0,0.0,0.01,"['sp2026']",2.0,,1,80.0,3.62,0,False,P,
"""


def test_parse_course_extracts_course_id_and_title() -> None:
    assert parse_course("ECE 408: Applied Parallel Programming") == (
        "ECE",
        "408",
        "ECE 408",
        "Applied Parallel Programming",
    )


def test_build_grade_distribution_parses_terms_and_grades() -> None:
    row = {
        "A+": "0.1",
        "A": "0.2",
        "term": "['fa2025']",
        "teaching_next_semester": "True",
    }
    distribution = build_grade_distribution(row)

    assert distribution["grades"]["A+"] == 0.1
    assert distribution["grades"]["A"] == 0.2
    assert distribution["terms"] == ["fa2025"]
    assert distribution["teaching_next_semester"] is True


def test_ingest_waf_gpa_csv_filters_subjects_and_upserts() -> None:
    session = Mock()
    with (
        patch("app.ingestion.gpa.upsert_course", return_value=True) as upsert_course,
        patch("app.ingestion.gpa.upsert_gpa_stat") as upsert_gpa_stat,
    ):
        result = ingest_waf_gpa_csv(
            session,
            CSV_FIXTURE,
            limit=20,
            source_url="https://example.com/final.csv",
        )

    assert result.rows_ingested == 2
    assert upsert_course.call_count == 2
    assert upsert_gpa_stat.call_count == 2
    assert upsert_course.call_args_list[0].kwargs["course_id"] == "CS 225"
    assert upsert_gpa_stat.call_args_list[0].kwargs["instructor_name"] == "Jane Doe"
    assert upsert_gpa_stat.call_args_list[0].kwargs["average_gpa"] == 3.45
    session.commit.assert_called_once()


def test_ingest_waf_gpa_csv_only_upserts_each_course_once_per_run() -> None:
    duplicate_course_csv = CSV_FIXTURE.replace(
        "ECE 408: Applied Parallel Programming,Applied Parallel Programming",
        "CS 225: Data Structures,Data Structures",
    )
    session = Mock()
    with (
        patch("app.ingestion.gpa.upsert_course", return_value=True) as upsert_course,
        patch("app.ingestion.gpa.upsert_gpa_stat") as upsert_gpa_stat,
    ):
        result = ingest_waf_gpa_csv(
            session,
            duplicate_course_csv,
            limit=20,
            source_url="https://example.com/final.csv",
        )

    assert result.rows_ingested == 2
    assert upsert_course.call_count == 1
    assert upsert_gpa_stat.call_count == 2
