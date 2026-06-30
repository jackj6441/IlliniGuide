import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course
from app.services.rag.normalize import extract_course_ids, normalize_course_id
from app.services.tools.schemas import PrerequisiteCheck


CLAUSE_PATTERN = re.compile(
    r"(?:Credit|Credit or concurrent registration|Concurrent registration)\s+in\s+"
    r"(.+?)(?=\s+(?:Credit|Credit or concurrent registration|Concurrent registration)\s+in\b|$)",
    re.IGNORECASE,
)


def check_prerequisites(
    session: Session,
    target_course: str,
    completed_courses: list[str] | None = None,
) -> PrerequisiteCheck | None:
    normalized_target = normalize_course_id(target_course)
    normalized_completed = [
        normalize_course_id(course_id) for course_id in (completed_courses or [])
    ]
    completed_set = set(normalized_completed)

    course = session.scalar(select(Course).where(Course.course_id == normalized_target))
    if course is None:
        return None

    prerequisites = (course.prerequisites or "").strip()
    if not prerequisites:
        return PrerequisiteCheck(
            target_course=normalized_target,
            completed_courses=normalized_completed,
            missing_prerequisites=[],
            readiness="likely_ready",
            notes=["No prerequisite text is listed for this course."],
        )

    prerequisite_groups = parse_prerequisite_groups(prerequisites)
    if not prerequisite_groups:
        return PrerequisiteCheck(
            target_course=normalized_target,
            completed_courses=normalized_completed,
            missing_prerequisites=[],
            readiness="unknown",
            notes=[
                "Prerequisite text does not contain parseable course IDs.",
                f"Raw prerequisite text: {prerequisites}",
            ],
        )

    missing_groups = [
        group for group in prerequisite_groups if completed_set.isdisjoint(group)
    ]
    if not missing_groups:
        return PrerequisiteCheck(
            target_course=normalized_target,
            completed_courses=normalized_completed,
            missing_prerequisites=[],
            readiness="likely_ready",
            notes=["All parseable course prerequisite groups are satisfied."],
        )

    return PrerequisiteCheck(
        target_course=normalized_target,
        completed_courses=normalized_completed,
        missing_prerequisites=[format_prerequisite_group(group) for group in missing_groups],
        readiness="missing_prerequisites",
        notes=[
            "This is a course-ID prerequisite check, not an official degree audit.",
            f"Raw prerequisite text: {prerequisites}",
        ],
    )


def parse_prerequisite_groups(prerequisites: str) -> list[list[str]]:
    groups: list[list[str]] = []
    for match in CLAUSE_PATTERN.finditer(prerequisites):
        course_ids = extract_course_ids(match.group(1))
        if course_ids:
            groups.append(course_ids)

    if groups:
        return groups

    course_ids = extract_course_ids(prerequisites)
    return [[course_id] for course_id in course_ids]


def format_prerequisite_group(group: list[str]) -> str:
    if len(group) == 1:
        return group[0]
    return " or ".join(group)
