from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import GPAStat
from app.services.rag.normalize import normalize_course_id
from app.services.tools.schemas import GPAStats, InstructorGPAStat


def get_gpa_stats(
    session: Session,
    course_id: str,
    instructor_name: str | None = None,
) -> GPAStats | None:
    normalized_course_id = normalize_course_id(course_id)
    statement = select(GPAStat).where(GPAStat.course_id == normalized_course_id)

    if instructor_name is not None and instructor_name.strip():
        normalized_instructor = instructor_name.strip().lower()
        statement = statement.where(
            func.lower(GPAStat.instructor_name).contains(normalized_instructor)
        )

    rows = list(session.scalars(statement).all())
    if not rows:
        return None

    average_values = [row.average_gpa for row in rows if row.average_gpa is not None]
    average_gpa = (
        round(sum(average_values) / len(average_values), 4) if average_values else None
    )

    return GPAStats(
        course_id=normalized_course_id,
        average_gpa=average_gpa,
        instructor_stats=[
            InstructorGPAStat(
                instructor_name=row.instructor_name,
                term=row.term,
                average_gpa=row.average_gpa,
                grade_distribution=row.grade_distribution,
                source_url=row.source_url,
            )
            for row in rows
        ],
    )
