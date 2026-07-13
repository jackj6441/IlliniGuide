from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.ingestion.course_catalog import (
    CourseIngestionResult,
    CourseUpsertAction,
    ingest_course_records,
    normalize_whitespace,
    upsert_source_course,
)


ECE_COURSES_SOURCE_URL = "https://ece.illinois.edu/academics/courses"


@dataclass(frozen=True)
class ECECourseRecord:
    course_id: str
    department: str
    course_number: str
    title: str
    prerequisites: str | None


ECEPrereqIngestionResult = CourseIngestionResult


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
    limit: int | None = None,
    source_url: str = ECE_COURSES_SOURCE_URL,
    commit: bool = True,
) -> ECEPrereqIngestionResult:
    return ingest_course_records(
        session,
        parse_ece_course_records(html_text),
        department="ECE",
        source_url=source_url,
        commit=commit,
        limit=limit,
        upsert=lambda current_session, record: upsert_course(
            current_session,
            record,  # type: ignore[arg-type]
            source_url=source_url,
        ),
    )


def upsert_course(
    session: Session,
    record: ECECourseRecord,
    *,
    source_url: str,
) -> CourseUpsertAction:
    return upsert_source_course(session, record, source_url=source_url)
