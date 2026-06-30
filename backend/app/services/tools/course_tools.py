from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course
from app.services.rag.normalize import normalize_course_id
from app.services.tools.schemas import CourseProfile


def get_course_profile(session: Session, course_id: str) -> CourseProfile | None:
    normalized_course_id = normalize_course_id(course_id)
    course = session.scalar(select(Course).where(Course.course_id == normalized_course_id))
    if course is None:
        return None
    return CourseProfile(
        course_id=course.course_id,
        title=course.title,
        description=course.description,
        credit_hours=course.credit_hours,
        prerequisites=course.prerequisites,
        career_tags=course.career_tags or [],
        source_url=course.source_url,
    )
