import pytest

from app.services.rag.embeddings import MockEmbeddingClient
from app.services.rag.retriever import RetrievedChunk
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


class FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeSession:
    """FakeSession supports both keyword (scalars) and semantic (execute) paths.

    ``semantic_rows`` are ``(CourseChunk, distance)`` tuples returned by
    ``execute(...).all()``. Empty by default so tests without explicit
    semantic data fall through to the keyword branch (matching pre-D5 behaviour).
    """

    def __init__(self, courses, *, semantic_rows=None):
        self._courses = courses
        self._semantic_rows = list(semantic_rows or [])

    def scalars(self, statement):
        return FakeScalars(self._courses)

    def execute(self, statement):
        return FakeExecuteResult(self._semantic_rows)


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


def test_direct_course_id_in_query_reaches_hybrid_metadata_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession([_make_course()])
    observed: dict[str, list[str] | None] = {}

    def fake_hybrid_search(session, query, client, *, course_ids, top_k):
        observed["course_ids"] = course_ids
        return [], []

    monkeypatch.setattr(
        "app.services.tools.search_tools.hybrid_search", fake_hybrid_search
    )

    result = search_course_docs(
        session,
        SearchCourseDocsRequest(query="What does ECE 408 cover?"),
    )

    assert result.course_ids == ["ECE 408"]
    assert observed["course_ids"] == ["ECE 408"]


def test_unknown_direct_course_id_returns_scoped_no_evidence_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession([_make_course(course_id="ECE 391")])
    observed: dict[str, list[str] | None] = {}

    def fake_hybrid_search(session, query, client, *, course_ids, top_k):
        observed["course_ids"] = course_ids
        return [], []

    monkeypatch.setattr(
        "app.services.tools.search_tools.hybrid_search", fake_hybrid_search
    )

    result = search_course_docs(
        session,
        SearchCourseDocsRequest(query="Tell me about ECE 999 Quantum Advising."),
    )

    assert result.docs == []
    assert observed["course_ids"] == ["ECE 999"]
    assert result.notes == [
        "No evidence found for requested course ID(s): ECE 999. "
        "The course may be outside the current catalog coverage.",
    ]


def test_rejects_conflicting_explicit_and_query_course_ids() -> None:
    with pytest.raises(ValueError, match="must match course IDs in query"):
        search_course_docs(
            FakeSession([_make_course()]),
            SearchCourseDocsRequest(
                query="Tell me about ECE 999.",
                course_ids=["ECE 391"],
            ),
        )


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


def _make_chunk_row(course_id: str, section_type: str = "overview", text: str = "text"):
    from app.db.models import CourseChunk

    return CourseChunk(
        course_id=course_id,
        source_name="UIUC Course Catalog",
        source_url=f"https://courses.illinois.edu/{course_id.replace(' ', '')}",
        section_type=section_type,
        chunk_text=text,
    )


def test_semantic_hit_high_confidence_produces_no_confidence_note() -> None:
    row = _make_chunk_row("ECE 391", "overview", "Systems programming.")
    session = FakeSession([], semantic_rows=[(row, 0.1)])  # similarity=0.9
    request = SearchCourseDocsRequest(query="systems programming", top_k=3)

    result = search_course_docs(
        session, request, embedding_client=MockEmbeddingClient()
    )

    assert result.docs[0].course_id == "ECE 391"
    assert result.docs[0].source_name == "UIUC Course Catalog"
    assert result.notes == []


def test_semantic_hit_low_confidence_appends_note() -> None:
    row = _make_chunk_row("ECE 391", "overview", "Systems programming.")
    session = FakeSession([], semantic_rows=[(row, 0.85)])  # similarity=0.15
    request = SearchCourseDocsRequest(query="something obscure", top_k=3)

    result = search_course_docs(
        session, request, embedding_client=MockEmbeddingClient()
    )

    assert len(result.docs) == 1
    assert result.notes
    assert "confidence low" in result.notes[0].lower()
    assert "0.15" in result.notes[0]


def test_semantic_empty_falls_back_to_keyword_silently() -> None:
    session = FakeSession(
        [_make_course()], semantic_rows=[]
    )
    request = SearchCourseDocsRequest(
        query="What is ECE 408 about GPU programming?", top_k=3
    )

    result = search_course_docs(
        session, request, embedding_client=MockEmbeddingClient()
    )

    # No "fallback" note; behaves like the pre-D5 keyword path.
    assert result.docs
    assert result.docs[0].course_id == "ECE 408"
    assert all("confidence" not in n.lower() for n in result.notes)


def test_embedding_client_defaults_when_omitted(monkeypatch) -> None:
    """When caller passes no client, we resolve one via the module singleton."""
    from app.services.rag import embeddings as emb_module

    sentinel = MockEmbeddingClient(model_name="sentinel-embedding")
    monkeypatch.setattr(emb_module, "_default_client", sentinel)

    session = FakeSession([_make_course()])
    request = SearchCourseDocsRequest(
        query="What is ECE 408 about GPU programming?", top_k=3
    )

    # No embedding_client passed; should resolve to `sentinel` and not crash.
    result = search_course_docs(session, request)

    assert result.docs
