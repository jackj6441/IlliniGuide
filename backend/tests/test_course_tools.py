import pytest

from app.services.tools.course_tools import get_course_profile


class FakeSession:
    def __init__(self, course):
        self.course = course

    def scalar(self, statement):
        return self.course


def test_get_course_profile_returns_structured_course_data() -> None:
    course = type(
        "Course",
        (),
        {
            "course_id": "ECE 210",
            "title": "Analog Signal Processing",
            "description": None,
            "credit_hours": "3",
            "prerequisites": "Credit in ECE 110",
            "career_tags": ["signals"],
            "source_url": "https://ece.illinois.edu/academics/courses",
        },
    )()

    profile = get_course_profile(FakeSession(course), "ece210")

    assert profile is not None
    assert profile.course_id == "ECE 210"
    assert profile.title == "Analog Signal Processing"
    assert profile.prerequisites == "Credit in ECE 110"
    assert profile.career_tags == ["signals"]
    assert profile.source_url == "https://ece.illinois.edu/academics/courses"


def test_get_course_profile_returns_none_for_missing_course() -> None:
    assert get_course_profile(FakeSession(None), "ECE 999") is None


def test_get_course_profile_rejects_invalid_course_id() -> None:
    with pytest.raises(ValueError):
        get_course_profile(FakeSession(None), "not a course")
