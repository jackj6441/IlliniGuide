import ast
import csv
from dataclasses import dataclass
from io import StringIO
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course, GPAStat


WAF_GPA_SOURCE_URL = (
    "https://waf.cs.illinois.edu/visualizations/"
    "Grade-Disparities-and-Accolades-by-Instructor/final.csv"
)
GRADE_COLUMNS = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F")


@dataclass(frozen=True)
class GPAIngestionResult:
    rows_seen: int
    rows_ingested: int
    courses_upserted: int
    source_url: str


def fetch_waf_gpa_csv(source_url: str = WAF_GPA_SOURCE_URL) -> str:
    request = Request(source_url, headers={"User-Agent": "IlliniGuideServe/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def ingest_waf_gpa_csv(
    session: Session,
    csv_text: str,
    *,
    limit: int = 20,
    subjects: tuple[str, ...] = ("CS", "ECE"),
    source_url: str = WAF_GPA_SOURCE_URL,
) -> GPAIngestionResult:
    rows_seen = 0
    rows_ingested = 0
    courses_upserted = 0
    seen_course_ids: set[str] = set()

    reader = csv.DictReader(StringIO(csv_text))
    for row in reader:
        rows_seen += 1
        parsed_course = parse_course(row["course"])
        if parsed_course is None:
            continue
        subject, course_number, course_id, title_from_course = parsed_course
        if subject not in subjects:
            continue

        if course_id not in seen_course_ids:
            course_was_created = upsert_course(
                session,
                course_id=course_id,
                department=subject,
                course_number=course_number,
                title=row.get("course_name") or title_from_course,
                source_url=source_url,
            )
            seen_course_ids.add(course_id)
            if course_was_created:
                courses_upserted += 1

        upsert_gpa_stat(
            session,
            course_id=course_id,
            instructor_name=format_instructor_name(row),
            term=row.get("term") or None,
            average_gpa=parse_optional_float(row.get("avg_gpa")),
            grade_distribution=build_grade_distribution(row),
            source_url=source_url,
        )
        rows_ingested += 1

        if rows_ingested >= limit:
            break

    session.commit()
    return GPAIngestionResult(
        rows_seen=rows_seen,
        rows_ingested=rows_ingested,
        courses_upserted=courses_upserted,
        source_url=source_url,
    )


def parse_course(value: str) -> tuple[str, str, str, str] | None:
    course_part, _, title = value.partition(":")
    pieces = course_part.strip().split()
    if len(pieces) < 2:
        return None
    subject = pieces[0].upper()
    number = pieces[1]
    if not number.isdigit():
        return None
    course_id = f"{subject} {number}"
    return subject, number, course_id, title.strip()


def format_instructor_name(row: dict[str, str]) -> str:
    last_name = (row.get("instructor") or "").strip()
    first_name = (row.get("instructor_first_name") or "").strip()
    if first_name and last_name:
        return f"{first_name} {last_name}"
    return first_name or last_name


def upsert_course(
    session: Session,
    *,
    course_id: str,
    department: str,
    course_number: str,
    title: str,
    source_url: str,
) -> bool:
    course = session.scalar(select(Course).where(Course.course_id == course_id))
    if course is None:
        session.add(
            Course(
                course_id=course_id,
                department=department,
                course_number=course_number,
                title=title,
                source_url=source_url,
            )
        )
        return True

    course.department = department
    course.course_number = course_number
    course.title = title
    course.source_url = source_url
    return False


def upsert_gpa_stat(
    session: Session,
    *,
    course_id: str,
    instructor_name: str,
    term: str | None,
    average_gpa: float | None,
    grade_distribution: dict,
    source_url: str,
) -> None:
    stat = session.scalar(
        select(GPAStat).where(
            GPAStat.course_id == course_id,
            GPAStat.instructor_name == instructor_name,
            GPAStat.term == term,
            GPAStat.source_url == source_url,
        )
    )
    if stat is None:
        session.add(
            GPAStat(
                course_id=course_id,
                instructor_name=instructor_name,
                term=term,
                average_gpa=average_gpa,
                grade_distribution=grade_distribution,
                source_url=source_url,
            )
        )
        return

    stat.average_gpa = average_gpa
    stat.grade_distribution = grade_distribution


def build_grade_distribution(row: dict[str, str]) -> dict:
    return {
        "grades": {grade: parse_optional_float(row.get(grade)) for grade in GRADE_COLUMNS},
        "terms": parse_term_list(row.get("term")),
        "num_sections": parse_optional_float(row.get("num_sections")),
        "num_semesters": parse_optional_float(row.get("num_semesters")),
        "num_students": parse_optional_float(row.get("num_students")),
        "num_excellence_awards": parse_optional_float(row.get("num_excellence_awards")),
        "num_outstanding_awards": parse_optional_float(row.get("num_outstanding_awards")),
        "total_faculty_awards": parse_optional_float(row.get("total_faculty_awards")),
        "rmp_num_reviews": parse_optional_float(row.get("rmp_num_reviews")),
        "rmp_rating": parse_optional_float(row.get("rmp_rating")),
        "teaching_next_semester": parse_bool(row.get("teaching_next_semester")),
        "gened": row.get("gened") or None,
        "uiuc_award": parse_list_string(row.get("uiuc_award")),
        "national_award": parse_list_string(row.get("national_award")),
    }


def parse_optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_bool(value: str | None) -> bool | None:
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def parse_term_list(value: str | None) -> list[str]:
    parsed = parse_list_string(value)
    return [str(item) for item in parsed]


def parse_list_string(value: str | None) -> list:
    if not value:
        return []
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return []
    if isinstance(parsed, list):
        return parsed
    return []
