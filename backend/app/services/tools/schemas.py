from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CourseProfile:
    course_id: str
    title: str
    description: str | None
    credit_hours: str | None
    prerequisites: str | None
    career_tags: list[str]
    source_url: str | None


@dataclass(frozen=True)
class InstructorGPAStat:
    instructor_name: str | None
    term: str | None
    average_gpa: float | None
    grade_distribution: dict[str, Any] | None
    source_url: str | None


@dataclass(frozen=True)
class GPAStats:
    course_id: str
    average_gpa: float | None
    instructor_stats: list[InstructorGPAStat]


@dataclass(frozen=True)
class PrerequisiteCheck:
    target_course: str
    completed_courses: list[str]
    missing_prerequisites: list[str]
    readiness: str
    notes: list[str]


@dataclass(frozen=True)
class CourseComparisonItem:
    course_id: str
    title: str | None
    career_tags: list[str]
    direction_match: str
    average_gpa: float | None
    prerequisite_readiness: str
    missing_prerequisites: list[str]
    notes: list[str]


@dataclass(frozen=True)
class CourseComparison:
    course_ids: list[str]
    dimension: str | None
    courses: list[CourseComparisonItem]
    notes: list[str]
