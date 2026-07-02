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


@dataclass(frozen=True)
class CourseRecommendation:
    course_id: str
    title: str
    score: float
    score_breakdown: dict[str, float]
    reason_codes: list[str]
    notes: list[str]


@dataclass(frozen=True)
class CourseRecommendations:
    target_direction: str
    completed_courses: list[str]
    recommendations: list[CourseRecommendation]
    notes: list[str]


@dataclass(frozen=True)
class SearchCourseDocsRequest:
    query: str
    course_ids: list[str] | None = None
    top_k: int = 5


@dataclass(frozen=True)
class RetrievedDoc:
    course_id: str
    source_name: str
    source_url: str
    section_type: str
    snippet: str
    score: float


@dataclass(frozen=True)
class SearchCourseDocsResult:
    query: str
    course_ids: list[str]
    docs: list[RetrievedDoc]
    notes: list[str]


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolPlan:
    intent: str
    course_ids: list[str]
    target_direction: str | None
    completed_courses: list[str]
    tool_calls: list[ToolCall]
    notes: list[str]
