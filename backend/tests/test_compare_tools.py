import pytest

from app.services.tools.compare_tools import compare_courses
from app.services.tools.schemas import CourseProfile, GPAStats, PrerequisiteCheck


def make_profile(course_id: str, title: str, career_tags: list[str]):
    return CourseProfile(
        course_id=course_id,
        title=title,
        description=None,
        credit_hours=None,
        prerequisites=None,
        career_tags=career_tags,
        source_url=None,
    )


def make_gpa_stats(course_id: str, average_gpa: float):
    return GPAStats(
        course_id=course_id,
        average_gpa=average_gpa,
        instructor_stats=[],
    )


def make_prereq_check(course_id: str, readiness="likely_ready"):
    return PrerequisiteCheck(
        target_course=course_id,
        completed_courses=[],
        missing_prerequisites=[],
        readiness=readiness,
        notes=[],
    )


def test_compare_courses_combines_profile_gpa_and_prerequisite_signals(monkeypatch):
    profiles = {
        "ECE 408": make_profile("ECE 408", "Applied Parallel Programming", ["ai_infra"]),
        "CS 433": make_profile("CS 433", "Computer System Organization", ["systems"]),
    }

    monkeypatch.setattr(
        "app.services.tools.compare_tools.get_course_profile",
        lambda session, course_id: profiles[course_id],
    )
    monkeypatch.setattr(
        "app.services.tools.compare_tools.get_gpa_stats",
        lambda session, course_id: make_gpa_stats(course_id, 3.5),
    )
    monkeypatch.setattr(
        "app.services.tools.compare_tools.check_prerequisites",
        lambda session, course_id, completed_courses=None: make_prereq_check(course_id),
    )

    comparison = compare_courses(object(), ["ece408", "cs433"], dimension="AI Infra")

    assert comparison.course_ids == ["ECE 408", "CS 433"]
    assert comparison.dimension == "ai_infra"
    assert comparison.courses[0].direction_match == "match"
    assert comparison.courses[0].average_gpa == 3.5
    assert comparison.courses[0].prerequisite_readiness == "likely_ready"
    assert comparison.courses[1].direction_match == "no_match"


def test_compare_courses_records_missing_profiles(monkeypatch):
    monkeypatch.setattr(
        "app.services.tools.compare_tools.get_course_profile",
        lambda session, course_id: None,
    )

    comparison = compare_courses(object(), ["ECE 408", "CS 433"])

    assert comparison.courses == []
    assert comparison.notes == [
        "No structured course profile found for ECE 408.",
        "No structured course profile found for CS 433.",
    ]


def test_compare_courses_marks_missing_gpa_and_prerequisite_data(monkeypatch):
    monkeypatch.setattr(
        "app.services.tools.compare_tools.get_course_profile",
        lambda session, course_id: make_profile(course_id, "Title", []),
    )
    monkeypatch.setattr(
        "app.services.tools.compare_tools.get_gpa_stats",
        lambda session, course_id: None,
    )
    monkeypatch.setattr(
        "app.services.tools.compare_tools.check_prerequisites",
        lambda session, course_id, completed_courses=None: None,
    )

    comparison = compare_courses(object(), ["ECE 408", "CS 433"])

    assert comparison.courses[0].average_gpa is None
    assert comparison.courses[0].prerequisite_readiness == "unknown"
    assert comparison.courses[0].notes == [
        "No GPA evidence is currently available.",
        "No prerequisite check is available.",
    ]


def test_compare_courses_requires_at_least_two_courses():
    with pytest.raises(ValueError, match="at least two"):
        compare_courses(object(), ["ECE 408"])


def test_compare_courses_rejects_invalid_course_id():
    with pytest.raises(ValueError):
        compare_courses(object(), ["ECE 408", "not a course"])
