from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course


CORE_COURSE_TAGS: dict[str, list[str]] = {
    "ECE 385": ["systems", "computer_architecture"],
    "ECE 391": ["systems", "software_engineering"],
    "ECE 407": ["security"],
    "ECE 408": ["ai_infra", "gpu_programming", "systems"],
    "ECE 411": ["computer_architecture", "systems", "ai_infra"],
    "ECE 419": ["security"],
    "ECE 422": ["security"],
    "ECE 428": ["systems"],
    "ECE 448": ["ai_ml"],
    "ECE 449": ["ai_ml", "data_science"],
    "ECE 470": ["robotics_cv"],
    "ECE 494": ["ai_ml", "robotics_cv"],
}


@dataclass(frozen=True)
class CareerTagSeedResult:
    rows_seen: int
    rows_updated: int
    rows_missing: int
    missing_course_ids: list[str]


def seed_core_career_tags(
    session: Session,
    tag_map: dict[str, list[str]] | None = None,
) -> CareerTagSeedResult:
    course_tags = tag_map or CORE_COURSE_TAGS
    rows_updated = 0
    missing_course_ids: list[str] = []

    for course_id, career_tags in course_tags.items():
        course = session.scalar(select(Course).where(Course.course_id == course_id))
        if course is None:
            missing_course_ids.append(course_id)
            continue

        course.career_tags = sorted(set(career_tags))
        rows_updated += 1

    session.commit()
    return CareerTagSeedResult(
        rows_seen=len(course_tags),
        rows_updated=rows_updated,
        rows_missing=len(missing_course_ids),
        missing_course_ids=missing_course_ids,
    )
