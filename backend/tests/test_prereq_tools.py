import pytest

from app.services.tools.prereq_tools import check_prerequisites


class FakeSession:
    def __init__(self, course):
        self.course = course

    def scalar(self, statement):
        return self.course


def make_course(course_id="ECE 391", prerequisites="Credit in CS 233 or ECE 220"):
    return type(
        "Course",
        (),
        {
            "course_id": course_id,
            "prerequisites": prerequisites,
        },
    )()


def test_check_prerequisites_returns_likely_ready_when_requirements_met() -> None:
    course = make_course("ECE 210", "Credit in ECE 110 Credit in PHYS 212")

    result = check_prerequisites(
        FakeSession(course),
        "ece210",
        ["ece110", "phys212"],
    )

    assert result is not None
    assert result.target_course == "ECE 210"
    assert result.completed_courses == ["ECE 110", "PHYS 212"]
    assert result.missing_prerequisites == []
    assert result.readiness == "likely_ready"


def test_check_prerequisites_reports_missing_course_groups() -> None:
    course = make_course("ECE 210", "Credit in ECE 110 Credit in PHYS 212")

    result = check_prerequisites(FakeSession(course), "ECE 210", ["ECE 110"])

    assert result is not None
    assert result.readiness == "missing_prerequisites"
    assert result.missing_prerequisites == ["PHYS 212"]


def test_check_prerequisites_accepts_one_course_from_or_group() -> None:
    course = make_course("ECE 391", "Credit in CS 233 or ECE 220")

    result = check_prerequisites(FakeSession(course), "ECE 391", ["ECE 220"])

    assert result is not None
    assert result.readiness == "likely_ready"
    assert result.missing_prerequisites == []


def test_check_prerequisites_returns_unknown_for_non_course_prerequisites() -> None:
    course = make_course("ECE 445", "Senior Standing")

    result = check_prerequisites(FakeSession(course), "ECE 445", [])

    assert result is not None
    assert result.readiness == "unknown"
    assert result.missing_prerequisites == []
    assert "parseable course IDs" in result.notes[0]


def test_check_prerequisites_returns_none_for_missing_target_course() -> None:
    assert check_prerequisites(FakeSession(None), "ECE 999", []) is None


def test_check_prerequisites_rejects_invalid_course_id() -> None:
    with pytest.raises(ValueError):
        check_prerequisites(FakeSession(None), "not a course", [])
