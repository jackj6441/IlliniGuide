import pytest

from app.services.tools.schemas import SearchCourseDocsRequest
from app.services.tools.search_tools import search_course_docs


def _make_course(**overrides):
    defaults = {
        "course_id": "ECE 408",
        "title": "Applied Parallel Programming",
        "description": "GPU programming, CUDA, and parallel algorithms.",
        "prerequisites": "Credit in ECE 391",
        "career_tags": ["ai_infra"],
        "source_url": "https://ece.illinois.edu/academics/courses",
    }
    defaults.update(overrides)
    return type("Course", (), defaults)()


class FakeScalars:
    def __init__(self, courses):
        self._courses = courses

    def all(self):
        return list(self._courses)


class FakeSession:
    def __init__(self, courses):
        self._courses = courses

    def scalars(self, statement):
        return FakeScalars(self._courses)


def test_happy_path_returns_ranked_docs_from_db() -> None:
    session = FakeSession([_make_course()])
    request = SearchCourseDocsRequest(query="What is ECE 408 about GPU programming?", top_k=3)

    result = search_course_docs(session, request)

    assert result.query == "What is ECE 408 about GPU programming?"
    assert result.docs
    assert result.docs[0].course_id == "ECE 408"
    assert result.docs[0].source_name == "Course Database"
    assert "GPU" in result.docs[0].snippet
    assert result.docs[0].score > 0
    assert result.notes == []


def test_normalizes_and_deduplicates_course_ids() -> None:
    session = FakeSession([_make_course()])
    request = SearchCourseDocsRequest(
        query="Tell me about parallel programming",
        course_ids=["ece408", "ECE-408", "ECE 408"],
        top_k=3,
    )

    result = search_course_docs(session, request)

    assert result.course_ids == ["ECE 408"]


def test_empty_query_raises() -> None:
    session = FakeSession([])
    with pytest.raises(ValueError, match="non-empty"):
        search_course_docs(session, SearchCourseDocsRequest(query="   ", top_k=3))


@pytest.mark.parametrize("bad_top_k", [0, -1, 21, 100])
def test_invalid_top_k_raises(bad_top_k: int) -> None:
    session = FakeSession([])
    with pytest.raises(ValueError, match="top_k"):
        search_course_docs(
            session, SearchCourseDocsRequest(query="ECE 408", top_k=bad_top_k)
        )


def test_invalid_course_id_raises() -> None:
    session = FakeSession([])
    with pytest.raises(ValueError, match="Invalid course id"):
        search_course_docs(
            session,
            SearchCourseDocsRequest(query="anything", course_ids=["not a course"]),
        )


def test_falls_back_to_sample_chunks_when_db_empty() -> None:
    session = FakeSession([])
    request = SearchCourseDocsRequest(query="What is ECE 391 about?", top_k=3)

    result = search_course_docs(session, request)

    assert result.docs
    assert result.docs[0].source_name == "Mock Course Dataset"
    assert result.notes == [
        "Fell back to sample chunks; course database has no matching evidence.",
    ]


def test_no_match_returns_empty_docs_with_note() -> None:
    session = FakeSession([])
    request = SearchCourseDocsRequest(
        query="topic completely unrelated xyzzy",
        top_k=3,
    )

    result = search_course_docs(session, request)

    assert result.docs == []
    assert result.notes == [
        "No evidence found in course database or sample chunks.",
    ]
