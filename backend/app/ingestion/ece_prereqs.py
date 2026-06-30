from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course


ECE_COURSES_SOURCE_URL = "https://ece.illinois.edu/academics/courses"


@dataclass(frozen=True)
class ECECourseRecord:
    course_id: str
    department: str
    course_number: str
    title: str
    prerequisites: str | None


@dataclass(frozen=True)
class ECEPrereqIngestionResult:
    rows_seen: int
    rows_ingested: int
    source_url: str


class ECECourseTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[ECECourseRecord] = []
        self._in_row = False
        self._current_class: str | None = None
        self._cells: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class")
        if tag == "tr":
            self._in_row = True
            self._cells = {"rubric": [], "title": [], "prereqs": []}
            return
        if self._in_row and tag == "td" and class_name in self._cells:
            self._current_class = class_name

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self._current_class = None
            return
        if tag == "tr" and self._in_row:
            self._append_current_record()
            self._in_row = False
            self._current_class = None

    def handle_data(self, data: str) -> None:
        if self._in_row and self._current_class:
            self._cells[self._current_class].append(data)

    def _append_current_record(self) -> None:
        rubric = normalize_whitespace(" ".join(self._cells["rubric"]))
        title = normalize_whitespace(" ".join(self._cells["title"]))
        prerequisites = normalize_whitespace(" ".join(self._cells["prereqs"]))
        if not rubric.startswith("ECE ") or not title:
            return
        parts = rubric.split()
        if len(parts) != 2 or not parts[1].isdigit():
            return
        self.records.append(
            ECECourseRecord(
                course_id=rubric,
                department="ECE",
                course_number=parts[1],
                title=title,
                prerequisites=prerequisites or None,
            )
        )


def fetch_ece_courses_html(source_url: str = ECE_COURSES_SOURCE_URL) -> str:
    request = Request(source_url, headers={"User-Agent": "IlliniGuideServe/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_ece_course_records(html_text: str) -> list[ECECourseRecord]:
    parser = ECECourseTableParser()
    parser.feed(html_text)
    return parser.records


def ingest_ece_prereqs_html(
    session: Session,
    html_text: str,
    *,
    limit: int = 20,
    source_url: str = ECE_COURSES_SOURCE_URL,
) -> ECEPrereqIngestionResult:
    rows_seen = 0
    rows_ingested = 0
    seen_course_ids: set[str] = set()

    for record in parse_ece_course_records(html_text):
        rows_seen += 1
        if record.course_id in seen_course_ids:
            continue

        upsert_course(session, record, source_url=source_url)
        seen_course_ids.add(record.course_id)
        rows_ingested += 1

        if rows_ingested >= limit:
            break

    session.commit()
    return ECEPrereqIngestionResult(
        rows_seen=rows_seen,
        rows_ingested=rows_ingested,
        source_url=source_url,
    )


def upsert_course(
    session: Session,
    record: ECECourseRecord,
    *,
    source_url: str,
) -> None:
    course = session.scalar(select(Course).where(Course.course_id == record.course_id))
    if course is None:
        session.add(
            Course(
                course_id=record.course_id,
                department=record.department,
                course_number=record.course_number,
                title=record.title,
                prerequisites=record.prerequisites,
                source_url=source_url,
            )
        )
        return

    course.department = record.department
    course.course_number = record.course_number
    course.title = record.title
    course.prerequisites = record.prerequisites
    course.source_url = source_url


def normalize_whitespace(value: str) -> str:
    return " ".join(unescape(value).split())
