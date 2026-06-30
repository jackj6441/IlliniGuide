import pytest

from app.services.tools.gpa_tools import get_gpa_stats


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def scalars(self, statement):
        self.statement = statement
        return FakeScalars(self.rows)


def make_gpa_row(
    instructor_name="Jane Doe",
    term="Fall 2025",
    average_gpa=3.5,
    grade_distribution=None,
    source_url="https://waf.cs.illinois.edu/visualizations/Grade-Disparities-and-Accolades-by-Instructor/",
):
    return type(
        "GPARow",
        (),
        {
            "instructor_name": instructor_name,
            "term": term,
            "average_gpa": average_gpa,
            "grade_distribution": grade_distribution or {"A": 10, "B": 4},
            "source_url": source_url,
        },
    )()


def test_get_gpa_stats_returns_course_average_and_instructor_rows() -> None:
    rows = [
        make_gpa_row(instructor_name="Jane Doe", average_gpa=3.4),
        make_gpa_row(instructor_name="John Smith", average_gpa=3.8),
    ]

    stats = get_gpa_stats(FakeSession(rows), "cs100")

    assert stats is not None
    assert stats.course_id == "CS 100"
    assert stats.average_gpa == 3.6
    assert len(stats.instructor_stats) == 2
    assert stats.instructor_stats[0].instructor_name == "Jane Doe"
    assert stats.instructor_stats[0].grade_distribution == {"A": 10, "B": 4}


def test_get_gpa_stats_returns_none_for_missing_course() -> None:
    assert get_gpa_stats(FakeSession([]), "ECE 999") is None


def test_get_gpa_stats_rejects_invalid_course_id() -> None:
    with pytest.raises(ValueError):
        get_gpa_stats(FakeSession([]), "not a course")


def test_get_gpa_stats_accepts_optional_instructor_filter() -> None:
    session = FakeSession([make_gpa_row(instructor_name="Jane Doe")])

    stats = get_gpa_stats(session, "CS 100", instructor_name="jane")

    assert stats is not None
    assert stats.instructor_stats[0].instructor_name == "Jane Doe"
    assert session.statement is not None
