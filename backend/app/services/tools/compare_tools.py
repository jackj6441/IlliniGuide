from sqlalchemy.orm import Session

from app.services.rag.normalize import normalize_course_id
from app.services.tools.course_tools import get_course_profile
from app.services.tools.gpa_tools import get_gpa_stats
from app.services.tools.prereq_tools import check_prerequisites
from app.services.tools.schemas import CourseComparison, CourseComparisonItem


def compare_courses(
    session: Session,
    course_ids: list[str],
    dimension: str | None = None,
    completed_courses: list[str] | None = None,
) -> CourseComparison:
    normalized_course_ids = [normalize_course_id(course_id) for course_id in course_ids]
    if len(normalized_course_ids) < 2:
        raise ValueError("compare_courses requires at least two course IDs")

    normalized_dimension = normalize_dimension(dimension)
    courses: list[CourseComparisonItem] = []
    notes: list[str] = []

    for course_id in normalized_course_ids:
        profile = get_course_profile(session, course_id)
        if profile is None:
            notes.append(f"No structured course profile found for {course_id}.")
            continue

        gpa_stats = get_gpa_stats(session, course_id)
        prerequisite_check = check_prerequisites(
            session,
            course_id,
            completed_courses=completed_courses,
        )

        item_notes: list[str] = []
        if gpa_stats is None:
            item_notes.append("No GPA evidence is currently available.")
        if prerequisite_check is None:
            item_notes.append("No prerequisite check is available.")

        courses.append(
            CourseComparisonItem(
                course_id=profile.course_id,
                title=profile.title,
                career_tags=profile.career_tags,
                direction_match=compute_direction_match(
                    profile.career_tags,
                    normalized_dimension,
                ),
                average_gpa=gpa_stats.average_gpa if gpa_stats else None,
                prerequisite_readiness=(
                    prerequisite_check.readiness if prerequisite_check else "unknown"
                ),
                missing_prerequisites=(
                    prerequisite_check.missing_prerequisites
                    if prerequisite_check
                    else []
                ),
                notes=item_notes,
            )
        )

    return CourseComparison(
        course_ids=normalized_course_ids,
        dimension=normalized_dimension,
        courses=courses,
        notes=notes,
    )


def normalize_dimension(dimension: str | None) -> str | None:
    if dimension is None:
        return None
    normalized = dimension.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized or None


def compute_direction_match(
    career_tags: list[str],
    dimension: str | None,
) -> str:
    if dimension is None:
        return "not_requested"
    normalized_tags = {normalize_dimension(tag) for tag in career_tags}
    if dimension in normalized_tags:
        return "match"
    return "no_match"
