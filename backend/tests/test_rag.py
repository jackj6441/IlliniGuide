import pytest

from app.services.rag.citation import citation_from_chunk
from app.services.rag.normalize import extract_course_ids, normalize_course_id
from app.services.rag.retriever import search_course_docs


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ece391", "ECE 391"),
        ("ECE391", "ECE 391"),
        ("cs 433", "CS 433"),
        ("ece-408", "ECE 408"),
    ],
)
def test_normalize_course_id(raw: str, expected: str) -> None:
    assert normalize_course_id(raw) == expected


def test_normalize_course_id_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        normalize_course_id("not a course")


def test_extract_course_ids_preserves_order_and_deduplicates() -> None:
    assert extract_course_ids("Compare ece408 with CS 433 and ECE 408") == [
        "ECE 408",
        "CS 433",
    ]


def test_search_course_docs_uses_course_filter_from_query() -> None:
    chunks = search_course_docs("What is ECE 391 about?", top_k=3)

    assert chunks
    assert chunks[0].course_id == "ECE 391"
    assert "systems programming" in chunks[0].chunk_text


def test_search_course_docs_returns_ai_infra_related_chunks() -> None:
    chunks = search_course_docs("Compare ECE 408 and CS 433 for AI infrastructure", top_k=5)
    course_ids = {chunk.course_id for chunk in chunks}

    assert {"ECE 408", "CS 433"}.issubset(course_ids)


def test_citation_from_chunk_preserves_source_metadata() -> None:
    chunk = search_course_docs("What is ECE 408?", top_k=1)[0]
    citation = citation_from_chunk(chunk)

    assert citation.course_id == "ECE 408"
    assert citation.source_name == "Mock Course Dataset"
    assert citation.source_url
    assert citation.snippet
