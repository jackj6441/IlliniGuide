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
