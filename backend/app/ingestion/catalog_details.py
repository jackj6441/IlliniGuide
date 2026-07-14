"""Ingest official UIUC catalog descriptions and credit hours for one department."""

from __future__ import annotations

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


ECE_CATALOG_DETAILS_SOURCE_URL = "https://catalog.illinois.edu/courses-of-instruction/ece/"
CS_CATALOG_DETAILS_SOURCE_URL = "https://catalog.illinois.edu/courses-of-instruction/cs/"
PREREQUISITE_PATTERN = re.compile(
    r"Prerequisite(?:\(s\)|s)?\s*:\s*(?P<value>.*?)(?=\n|$)", re.IGNORECASE
)


@dataclass(frozen=True)
class CatalogCourseRecord:
    course_id: str
    department: str
    course_number: str
    title: str
    prerequisites: str | None
    description: str | None
    credit_hours: str | None


class CatalogDetailParser(HTMLParser):
    """Parse current UIUC catalog ``courseblock`` markup for one department."""

    def __init__(self, department: str) -> None:
        super().__init__()
        self._department = department
        self._heading_pattern = re.compile(
            rf"^{re.escape(department)}\s+(?P<number>\d{{3,4}}[A-Z]?)\s+"
            r"(?P<title>.+?)\s+credit:\s*(?P<credits>.+?)$",
            re.IGNORECASE,
        )
        self.records: list[CatalogCourseRecord] = []
        self._in_heading = False
        self._in_description = False
        self._heading_parts: list[str] = []
        self._description_parts: list[str] = []
        self._current: tuple[str, str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        class_names = set((dict(attrs).get("class") or "").split())
        if "courseblocktitle" in class_names:
            self._flush_current()
            self._in_heading = True
            self._heading_parts = []
            return
        if self._current is not None and "courseblockdesc" in class_names:
            self._in_description = True
        if self._current is not None and tag in {"p", "br", "li", "div"}:
            self._description_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._in_heading:
            self._in_heading = False
            self._start_course_from_heading()
        elif tag == "p" and self._in_description:
            self._in_description = False
        if self._current is not None and tag in {"p", "li", "div"}:
            self._description_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._heading_parts.append(data)
        elif self._current is not None and self._in_description:
            self._description_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush_current()

    def _start_course_from_heading(self) -> None:
        heading = normalize_whitespace(" ".join(self._heading_parts))
        match = self._heading_pattern.match(heading)
        if match is None:
            self._current = None
            return
        self._current = (
            match.group("number").upper(),
            normalize_whitespace(match.group("title")),
            normalize_whitespace(match.group("credits")).rstrip("."),
        )
        self._description_parts = []

    def _flush_current(self) -> None:
        if self._current is None:
            return
        number, title, credit_hours = self._current
        body = "".join(self._description_parts)
        prerequisite_match = PREREQUISITE_PATTERN.search(body)
        prerequisites = (
            normalize_whitespace(prerequisite_match.group("value"))
            if prerequisite_match is not None
            else None
        )
        description = normalize_whitespace(
            body[: prerequisite_match.start()] if prerequisite_match is not None else body
        )
        self.records.append(
            CatalogCourseRecord(
                course_id=f"{self._department} {number}",
                department=self._department,
                course_number=number,
                title=title,
                prerequisites=prerequisites or None,
                description=description or None,
                credit_hours=credit_hours or None,
            )
        )
        self._current = None
        self._description_parts = []


def fetch_catalog_details_html(source_url: str) -> str:
    request = Request(source_url, headers={"User-Agent": "IlliniGuideServe/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_catalog_detail_records(html_text: str, *, department: str) -> list[CatalogCourseRecord]:
    parser = CatalogDetailParser(department)
    parser.feed(html_text)
    parser.close()
    return parser.records


def ingest_catalog_details_html(
    session: Session,
    html_text: str,
    *,
    department: str,
    source_url: str,
    limit: int | None = None,
    commit: bool = True,
) -> CourseIngestionResult:
    return ingest_course_records(
        session,
        parse_catalog_detail_records(html_text, department=department),
        department=department,
        source_url=source_url,
        limit=limit,
        commit=commit,
        upsert=lambda current_session, record: upsert_catalog_detail(
            current_session, record, source_url=source_url
        ),
    )


def upsert_catalog_detail(
    session: Session, record: CatalogCourseRecord, *, source_url: str
) -> CourseUpsertAction:
    return upsert_source_course(session, record, source_url=source_url)
