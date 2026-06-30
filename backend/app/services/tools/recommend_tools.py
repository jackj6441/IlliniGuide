from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course
from app.services.rag.normalize import normalize_course_id
from app.services.tools.compare_tools import normalize_dimension
from app.services.tools.gpa_tools import get_gpa_stats
from app.services.tools.prereq_tools import check_prerequisites
from app.services.tools.schemas import CourseRecommendation, CourseRecommendations


def recommend_courses(
    session: Session,
    target_direction: str,
    completed_courses: list[str] | None = None,
    max_results: int = 5,
) -> CourseRecommendations:
    normalized_direction = normalize_dimension(target_direction)
    if normalized_direction is None:
        raise ValueError("target_direction is required")
    if max_results < 1:
        raise ValueError("max_results must be at least 1")

    normalized_completed = [
        normalize_course_id(course_id) for course_id in (completed_courses or [])
    ]
    completed_set = set(normalized_completed)

    candidates = list(session.scalars(select(Course).order_by(Course.course_id)).all())
    recommendations: list[CourseRecommendation] = []

    for course in candidates:
        if course.course_id in completed_set:
            continue

        career_tags = course.career_tags or []
        prerequisite_check = check_prerequisites(
            session,
            course.course_id,
            completed_courses=normalized_completed,
        )
        gpa_stats = get_gpa_stats(session, course.course_id)

        score_breakdown = {
            "direction_match": direction_match_score(career_tags, normalized_direction),
            "prerequisite_readiness": prerequisite_readiness_score(prerequisite_check),
            "course_level_progression": course_level_progression_score(
                course.course_number
            ),
            "gpa_risk": gpa_risk_score(gpa_stats.average_gpa if gpa_stats else None),
        }
        if score_breakdown["direction_match"] <= 0:
            continue

        score = round(
            0.40 * score_breakdown["direction_match"]
            + 0.25 * score_breakdown["prerequisite_readiness"]
            + 0.20 * score_breakdown["course_level_progression"]
            + 0.15 * score_breakdown["gpa_risk"],
            4,
        )

        if score <= 0:
            continue

        recommendations.append(
            CourseRecommendation(
                course_id=course.course_id,
                title=course.title,
                score=score,
                score_breakdown=score_breakdown,
                reason_codes=reason_codes(
                    career_tags=career_tags,
                    target_direction=normalized_direction,
                    prerequisite_readiness=(
                        prerequisite_check.readiness if prerequisite_check else "unknown"
                    ),
                    average_gpa=gpa_stats.average_gpa if gpa_stats else None,
                ),
                notes=recommendation_notes(prerequisite_check, gpa_stats is not None),
            )
        )

    recommendations.sort(key=lambda item: (-item.score, item.course_id))
    return CourseRecommendations(
        target_direction=normalized_direction,
        completed_courses=normalized_completed,
        recommendations=recommendations[:max_results],
        notes=[
            "Scores are internal debug signals and should not be shown in normal UI.",
            "This is an initial rule-based recommender, not an official advising plan.",
            "Courses without matching career tags are excluded in this first version.",
        ],
    )


def direction_match_score(career_tags: list[str], target_direction: str) -> float:
    normalized_tags = {normalize_dimension(tag) for tag in career_tags}
    if target_direction in normalized_tags:
        return 1.0
    if target_direction.replace("_", "") in {
        (tag or "").replace("_", "") for tag in normalized_tags
    }:
        return 0.75
    return 0.0


def prerequisite_readiness_score(prerequisite_check) -> float:
    if prerequisite_check is None:
        return 0.5
    if prerequisite_check.readiness == "likely_ready":
        return 1.0
    if prerequisite_check.readiness == "unknown":
        return 0.5
    return 0.0


def course_level_progression_score(course_number: str) -> float:
    try:
        number = int(course_number)
    except ValueError:
        return 0.5
    if number < 300:
        return 0.6
    if number < 500:
        return 1.0
    return 0.7


def gpa_risk_score(average_gpa: float | None) -> float:
    if average_gpa is None:
        return 0.5
    if average_gpa >= 3.5:
        return 1.0
    if average_gpa >= 3.0:
        return 0.75
    if average_gpa >= 2.5:
        return 0.45
    return 0.2


def reason_codes(
    career_tags: list[str],
    target_direction: str,
    prerequisite_readiness: str,
    average_gpa: float | None,
) -> list[str]:
    codes: list[str] = []
    if direction_match_score(career_tags, target_direction) > 0:
        codes.append(f"{target_direction}_match")
    if prerequisite_readiness == "likely_ready":
        codes.append("prerequisites_satisfied")
    elif prerequisite_readiness == "missing_prerequisites":
        codes.append("missing_prerequisites")
    if average_gpa is not None:
        codes.append("has_gpa_evidence")
    return codes


def recommendation_notes(prerequisite_check, has_gpa_evidence: bool) -> list[str]:
    notes: list[str] = []
    if prerequisite_check is None:
        notes.append("No prerequisite data is available for this course.")
    elif prerequisite_check.readiness == "unknown":
        notes.extend(prerequisite_check.notes)
    elif prerequisite_check.missing_prerequisites:
        notes.append(
            "Missing prerequisites: "
            + ", ".join(prerequisite_check.missing_prerequisites)
        )
    if not has_gpa_evidence:
        notes.append("No GPA evidence is currently available.")
    return notes
