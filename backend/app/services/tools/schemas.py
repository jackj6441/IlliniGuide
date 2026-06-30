from dataclasses import dataclass


@dataclass(frozen=True)
class CourseProfile:
    course_id: str
    title: str
    description: str | None
    credit_hours: str | None
    prerequisites: str | None
    career_tags: list[str]
    source_url: str | None
