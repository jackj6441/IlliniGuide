"""Unit tests for the pgvector semantic search wrapper.

Uses a mock Session so we don't need a running Postgres. Tests focus on:
- embedding-client contract (called exactly once per query)
- SQL shape (uses `<=>`, filters NULL embeddings, respects `course_ids`)
- distance→similarity conversion + clipping
- top_k short-circuit
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.db.models import CourseChunk
from app.services.rag.embeddings import MockEmbeddingClient
from app.services.rag.pgvector_retriever import semantic_search
from app.services.rag.retriever import RetrievedChunk


def _make_chunk_row(
    course_id: str,
    section_type: str = "overview",
    chunk_text: str = "sample text",
) -> CourseChunk:
    return CourseChunk(
        course_id=course_id,
        source_name="UIUC Course Catalog",
        source_url=f"https://courses.illinois.edu/{course_id.replace(' ', '')}",
        section_type=section_type,
        chunk_text=chunk_text,
    )


def _mock_session_returning(rows: list[tuple[CourseChunk, float]]) -> MagicMock:
    session = MagicMock()
    session.execute.return_value.all.return_value = rows
    return session


def test_top_k_zero_short_circuits_without_touching_db_or_client() -> None:
    session = MagicMock()
    client = MagicMock()

    out = semantic_search(session, "anything", client, top_k=0)

    assert out == []
    client.embed.assert_not_called()
    session.execute.assert_not_called()


def test_negative_top_k_short_circuits() -> None:
    session = MagicMock()
    client = MagicMock()
    assert semantic_search(session, "q", client, top_k=-1) == []
    client.embed.assert_not_called()


def test_embed_called_once_per_query() -> None:
    session = _mock_session_returning([])
    client = MagicMock()
    client.embed.return_value = [[0.1] * 384]

    semantic_search(session, "prereqs of ECE 391?", client, top_k=5)

    assert client.embed.call_count == 1
    args, _ = client.embed.call_args
    assert args[0] == ["prereqs of ECE 391?"]


def test_returns_retrieved_chunks_with_similarity() -> None:
    rows = [
        (_make_chunk_row("ECE 391", "prerequisites", "ECE 220."), 0.10),
        (_make_chunk_row("ECE 408", "overview", "CUDA parallel programming."), 0.25),
    ]
    session = _mock_session_returning(rows)
    client = MockEmbeddingClient()

    out = semantic_search(session, "systems programming", client, top_k=5)

    assert len(out) == 2
    assert all(isinstance(c, RetrievedChunk) for c in out)
    assert out[0].course_id == "ECE 391"
    assert out[0].score == pytest.approx(0.9, abs=1e-4)
    assert out[1].score == pytest.approx(0.75, abs=1e-4)


def test_similarity_clipped_to_unit_interval() -> None:
    """Guards against tiny negative floats or distance > 1 edge cases."""
    rows = [
        (_make_chunk_row("A"), -1e-12),  # would produce 1.0 + epsilon
        (_make_chunk_row("B"), 1.7),  # opposite direction → negative similarity
    ]
    session = _mock_session_returning(rows)
    client = MagicMock()
    client.embed.return_value = [[0.0] * 384]

    out = semantic_search(session, "q", client, top_k=5)

    assert 0.0 <= out[0].score <= 1.0
    assert 0.0 <= out[1].score <= 1.0
    assert out[0].score == pytest.approx(1.0)
    assert out[1].score == pytest.approx(0.0)


def test_uses_pgvector_cosine_operator_and_null_filter() -> None:
    session = _mock_session_returning([])
    client = MagicMock()
    client.embed.return_value = [[0.5] * 384]

    semantic_search(session, "q", client, top_k=5)

    executed_stmt = session.execute.call_args.args[0]
    rendered = str(executed_stmt).lower()
    assert "<=>" in rendered
    assert "embedding is not null" in rendered
    assert "limit" in rendered


def test_course_ids_filter_produces_in_clause() -> None:
    session = _mock_session_returning([])
    client = MagicMock()
    client.embed.return_value = [[0.5] * 384]

    semantic_search(
        session, "q", client, course_ids=["ECE 391", "ECE 408"], top_k=3
    )

    rendered = str(session.execute.call_args.args[0]).lower()
    assert "course_chunks.course_id in" in rendered


def test_no_course_ids_filter_when_empty_list() -> None:
    session = _mock_session_returning([])
    client = MagicMock()
    client.embed.return_value = [[0.5] * 384]

    semantic_search(session, "q", client, course_ids=[], top_k=3)

    rendered = str(session.execute.call_args.args[0]).lower()
    assert "course_chunks.course_id in" not in rendered


def test_result_preserves_fields_from_chunk_row() -> None:
    row = _make_chunk_row(
        "ECE 408",
        section_type="career_direction",
        chunk_text="Suitable for AI infrastructure roles.",
    )
    session = _mock_session_returning([(row, 0.2)])
    client = MockEmbeddingClient()

    out = semantic_search(session, "gpu programming", client, top_k=1)

    assert out[0].section_type == "career_direction"
    assert out[0].chunk_text == "Suitable for AI infrastructure roles."
    assert out[0].source_name == "UIUC Course Catalog"
    assert out[0].source_url.endswith("ECE408")


def test_empty_result_set_returns_empty_list() -> None:
    session = _mock_session_returning([])
    client = MockEmbeddingClient()

    assert semantic_search(session, "q", client, top_k=5) == []
