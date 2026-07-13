"""Parse and ingest the official UIUC CS course-catalog page."""

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.ingestion.course_catalog import (
    CourseIngestionResult,
    CourseUpsertAction,
    ingest_course_records,
    normalize_whitespace,
    upsert_source_course,
)


CS_COURSES_SOURCE_URL = "https://catalog.illinois.edu/courses-of-instruction/cs/"
COURSE_HEADING_PATTERN = re.compile(
    r"^CS\s+(?P<number>\d{3,4}[A-Z]?)\s+(?P<title>.+?)\s+credit:\s*",
    re.IGNORECASE,
)
PREREQUISITE_PATTERN = re.compile(
    r"Prerequisite(?:\(s\)|s)?\s*:\s*(?P<value>.*?)(?=\n|$)", re.IGNORECASE
)


@dataclass(frozen=True)
class CSCourseRecord:
    course_id: str
    department: str
    course_number: str
    title: str
    prerequisites: str | None


CSCatalogIngestionResult = CourseIngestionResult


class CSCourseCatalogParser(HTMLParser):
    """Extract CS course headings and adjacent prerequisite text.

    The catalog currently uses ``p.courseblocktitle`` headings, while a legacy
    fixture uses ``h3``. We intentionally keep prerequisite text as source
    text: converting it into a prerequisite graph is a separate, later
    validation task.
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[CSCourseRecord] = []
        self._in_heading = False
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._body_parts: list[str] = []
        self._current: tuple[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        class_names = set((attributes.get("class") or "").split())
        if tag == "h3" or "courseblocktitle" in class_names:
            self._flush_current()
            self._in_heading = True
            self._heading_tag = tag
            self._heading_parts = []
        elif self._current is not None and tag in {"p", "br", "li", "div"}:
            self._body_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading_tag and self._in_heading:
            self._in_heading = False
            self._heading_tag = None
            self._start_course_from_heading()
        elif self._current is not None and tag in {"p", "li", "div"}:
            self._body_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._heading_parts.append(data)
        elif self._current is not None:
            self._body_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush_current()

    def _start_course_from_heading(self) -> None:
        heading = normalize_whitespace(" ".join(self._heading_parts))
        match = COURSE_HEADING_PATTERN.match(heading)
        if match is None:
            self._current = None
            return
        number = match.group("number").upper()
        title = normalize_whitespace(match.group("title"))
        self._current = (number, title)
        self._body_parts = []

    def _flush_current(self) -> None:
        if self._current is None:
            return
        number, title = self._current
        body = "".join(self._body_parts)
        prerequisite_match = PREREQUISITE_PATTERN.search(body)
        prerequisites = (
            normalize_whitespace(prerequisite_match.group("value"))
            if prerequisite_match is not None
            else None
        )
        self.records.append(
            CSCourseRecord(
                course_id=f"CS {number}",
                department="CS",
                course_number=number,
                title=title,
                prerequisites=prerequisites or None,
            )
        )
        self._current = None
        self._body_parts = []


def fetch_cs_courses_html(source_url: str = CS_COURSES_SOURCE_URL) -> str:
    request = Request(source_url, headers={"User-Agent": "IlliniGuideServe/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_cs_course_records(html_text: str) -> list[CSCourseRecord]:
    parser = CSCourseCatalogParser()
    parser.feed(html_text)
    parser.close()
    return parser.records


def ingest_cs_courses_html(
    session: Session,
    html_text: str,
    *,
    limit: int | None = None,
    source_url: str = CS_COURSES_SOURCE_URL,
    commit: bool = True,
) -> CSCatalogIngestionResult:
    return ingest_course_records(
        session,
        parse_cs_course_records(html_text),
        department="CS",
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
    record: CSCourseRecord,
    *,
    source_url: str,
) -> CourseUpsertAction:
    return upsert_source_course(session, record, source_url=source_url)
