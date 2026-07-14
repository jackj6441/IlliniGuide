"""Shared ingestion mechanics for source-tagged department course catalogs.

Parsers stay department-specific because their source HTML differs. This module
owns the repeatable parts: identity validation, per-run de-duplication,
idempotent persistence accounting, and JSON audit manifests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Literal, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course


CourseUpsertAction = Literal["inserted", "updated"]
COURSE_ID_PATTERN = re.compile(r"^([A-Z]{2,8}) (\d{3,4}[A-Z]?)$")


def normalize_whitespace(value: str) -> str:
    """Collapse source HTML text into a stable, comparison-friendly value."""
    from html import unescape

    return " ".join(unescape(value).split())


class CourseRecord(Protocol):
    course_id: str
    department: str
    course_number: str
    title: str
    prerequisites: str | None
    description: str | None
    credit_hours: str | None


@dataclass(frozen=True)
class CourseIngestionResult:
    department: str
    source_url: str
    parsed_count: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    duplicate_count: int

    @property
    def rows_seen(self) -> int:
        """Compatibility name used by the original ECE CLI output."""
        return self.parsed_count

    @property
    def rows_ingested(self) -> int:
        return self.inserted_count + self.updated_count

    def as_manifest_entry(self) -> dict[str, object]:
        return {
            "department": self.department,
            "source_url": self.source_url,
            "parsed_count": self.parsed_count,
            "inserted_count": self.inserted_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "duplicate_count": self.duplicate_count,
        }


def ingest_course_records(
    session: Session,
    records: Iterable[CourseRecord],
    *,
    department: str,
    source_url: str,
    upsert: Callable[[Session, CourseRecord], CourseUpsertAction | object],
    limit: int | None = None,
    commit: bool = True,
) -> CourseIngestionResult:
    """Upsert one department's parsed records without creating duplicate rows.

    ``limit`` is intentionally optional: a live run can ingest all records,
    while tests and incremental backfills can still use a bounded slice.
    """
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1 when provided")
    if not source_url.strip():
        raise ValueError("source_url must be non-empty")

    parsed_count = inserted_count = updated_count = skipped_count = duplicate_count = 0
    seen_course_ids: set[str] = set()
    accepted_count = 0

    for record in records:
        parsed_count += 1
        if not _is_valid_record(record, department):
            skipped_count += 1
            continue
        if record.course_id in seen_course_ids:
            duplicate_count += 1
            continue
        if limit is not None and accepted_count >= limit:
            continue

        action = upsert(session, record)
        seen_course_ids.add(record.course_id)
        accepted_count += 1
        # Treat a mocked/legacy return as inserted. Real implementations only
        # return the two explicit literals above.
        if action == "updated":
            updated_count += 1
        else:
            inserted_count += 1

    if commit:
        session.commit()
    return CourseIngestionResult(
        department=department,
        source_url=source_url,
        parsed_count=parsed_count,
        inserted_count=inserted_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        duplicate_count=duplicate_count,
    )


def upsert_source_course(
    session: Session,
    record: CourseRecord,
    *,
    source_url: str,
) -> CourseUpsertAction:
    """Persist source-tagged course data and report whether it was created."""
    course = session.scalar(select(Course).where(Course.course_id == record.course_id))
    description = (record.description or "").strip()
    credit_hours = (record.credit_hours or "").strip()
    if course is None:
        session.add(
            Course(
                course_id=record.course_id,
                department=record.department,
                course_number=record.course_number,
                title=record.title,
                prerequisites=record.prerequisites,
                description=description or None,
                credit_hours=credit_hours or None,
                source_url=source_url,
            )
        )
        return "inserted"

    course.department = record.department
    course.course_number = record.course_number
    course.title = record.title
    if record.prerequisites is not None:
        course.prerequisites = record.prerequisites
    if description:
        course.description = description
    if credit_hours:
        course.credit_hours = credit_hours
    course.source_url = source_url
    return "updated"


def write_ingestion_manifest(
    artifacts_root: Path,
    results: Iterable[CourseIngestionResult],
    *,
    fetched_at: datetime,
    run_id: str | None = None,
    total_distinct_course_count: int | None = None,
) -> Path:
    """Write one machine-readable runtime artifact; never write into source docs."""
    run_id = run_id or _default_run_id()
    manifest_dir = _artifact_run_directory(artifacts_root, run_id)
    manifest_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = manifest_dir / "manifest.json"
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
        "departments": [result.as_manifest_entry() for result in results],
    }
    if total_distinct_course_count is not None:
        payload["total_distinct_course_count"] = total_distinct_course_count
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_valid_record(record: CourseRecord, expected_department: str) -> bool:
    match = COURSE_ID_PATTERN.fullmatch(record.course_id.strip())
    return bool(
        match
        and match.group(1) == expected_department
        and record.department == expected_department
        and record.course_number == match.group(2)
        and record.title.strip()
    )


def _default_run_id() -> str:
    return f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def _artifact_run_directory(artifacts_root: Path, run_id: str) -> Path:
    """Resolve a single artifact-run directory without allowing path traversal."""
    candidate = Path(run_id)
    if not run_id or candidate.is_absolute() or candidate.name != run_id or run_id in {".", ".."}:
        raise ValueError("run_id must be a single directory name inside artifacts_root")

    root = artifacts_root.resolve()
    run_directory = (root / candidate).resolve()
    if run_directory.parent != root:
        raise ValueError("run_id must resolve inside artifacts_root")
    return run_directory
