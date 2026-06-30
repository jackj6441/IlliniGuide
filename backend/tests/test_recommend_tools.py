import pytest

from app.services.tools.recommend_tools import recommend_courses
from app.services.tools.schemas import GPAStats, PrerequisiteCheck


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, courses):
        self.courses = courses

    def scalars(self, statement):
        return FakeScalars(self.courses)


def make_course(course_id, title, career_tags):
    department, course_number = course_id.split()
    return type(
        "Course",
        (),
        {
            "course_id": course_id,
            "department": department,
            "course_number": course_number,
            "title": title,
            "career_tags": career_tags,
        },
    )()


def make_prereq(course_id, readiness="likely_ready", missing=None):
    return PrerequisiteCheck(
        target_course=course_id,
        completed_courses=[],
        missing_prerequisites=missing or [],
        readiness=readiness,
        notes=[],
    )


def make_gpa(course_id, average_gpa):
    return GPAStats(course_id=course_id, average_gpa=average_gpa, instructor_stats=[])


def test_recommend_courses_ranks_direction_matches_first(monkeypatch):
    courses = [
        make_course("ECE 408", "Applied Parallel Programming", ["ai_infra"]),
        make_course("ECE 310", "Digital Signal Processing", ["signals"]),
    ]
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.check_prerequisites",
        lambda session, course_id, completed_courses=None: make_prereq(course_id),
    )
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.get_gpa_stats",
        lambda session, course_id: make_gpa(course_id, 3.7),
    )

    result = recommend_courses(FakeSession(courses), "AI Infra", max_results=2)

    assert result.target_direction == "ai_infra"
    assert result.recommendations[0].course_id == "ECE 408"
    assert [item.course_id for item in result.recommendations] == ["ECE 408"]
    assert result.recommendations[0].score_breakdown["direction_match"] == 1.0
    assert "ai_infra_match" in result.recommendations[0].reason_codes


def test_recommend_courses_excludes_courses_without_direction_match(monkeypatch):
    courses = [make_course("ECE 310", "Digital Signal Processing", ["signals"])]
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.check_prerequisites",
        lambda session, course_id, completed_courses=None: make_prereq(course_id),
    )
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.get_gpa_stats",
        lambda session, course_id: make_gpa(course_id, 3.9),
    )

    result = recommend_courses(FakeSession(courses), "ai_infra")

    assert result.recommendations == []


def test_recommend_courses_penalizes_missing_prerequisites(monkeypatch):
    courses = [make_course("ECE 408", "Applied Parallel Programming", ["ai_infra"])]
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.check_prerequisites",
        lambda session, course_id, completed_courses=None: make_prereq(
            course_id,
            readiness="missing_prerequisites",
            missing=["ECE 220"],
        ),
    )
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.get_gpa_stats",
        lambda session, course_id: make_gpa(course_id, 3.7),
    )

    result = recommend_courses(FakeSession(courses), "ai_infra")

    recommendation = result.recommendations[0]
    assert recommendation.score_breakdown["prerequisite_readiness"] == 0.0
    assert "missing_prerequisites" in recommendation.reason_codes
    assert recommendation.notes == ["Missing prerequisites: ECE 220"]


def test_recommend_courses_skips_completed_courses(monkeypatch):
    courses = [make_course("ECE 408", "Applied Parallel Programming", ["ai_infra"])]
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.check_prerequisites",
        lambda session, course_id, completed_courses=None: make_prereq(course_id),
    )
    monkeypatch.setattr(
        "app.services.tools.recommend_tools.get_gpa_stats",
        lambda session, course_id: make_gpa(course_id, 3.7),
    )

    result = recommend_courses(
        FakeSession(courses),
        "ai_infra",
        completed_courses=["ece408"],
    )

    assert result.completed_courses == ["ECE 408"]
    assert result.recommendations == []


def test_recommend_courses_returns_empty_results_for_empty_candidate_set():
    result = recommend_courses(FakeSession([]), "systems")

    assert result.recommendations == []
    assert "internal debug signals" in result.notes[0]


def test_recommend_courses_rejects_empty_direction():
    with pytest.raises(ValueError, match="target_direction"):
        recommend_courses(FakeSession([]), " ")


def test_recommend_courses_rejects_invalid_max_results():
    with pytest.raises(ValueError, match="max_results"):
        recommend_courses(FakeSession([]), "systems", max_results=0)
