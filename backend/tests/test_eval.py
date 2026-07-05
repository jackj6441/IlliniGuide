"""Unit tests for the retrieval eval harness.

We stub `semantic_search` so we can control what "the retriever returned"
without needing a real pgvector-backed session. This validates the scoring
logic (top1/topk/section_type accounting) in isolation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.rag.eval import (
    EvalCase,
    EvalReport,
    evaluate,
    format_report,
)
from app.services.rag.retriever import RetrievedChunk


def _chunk(course_id: str, section_type: str = "overview", score: float = 0.9):
    return RetrievedChunk(
        course_id=course_id,
        source_name="UIUC Course Catalog",
        source_url=f"https://courses.illinois.edu/{course_id.replace(' ', '')}",
        section_type=section_type,
        chunk_text=f"{course_id} content",
        score=score,
    )


def _patch_semantic(monkeypatch: pytest.MonkeyPatch, chunks_by_query):
    def fake_semantic_search(session, query, embedding_client, **kwargs):
        return chunks_by_query.get(query, [])

    monkeypatch.setattr(
        "app.services.rag.eval.semantic_search", fake_semantic_search
    )


def test_all_hit_top1_gives_full_score(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        EvalCase(query="q1", expected_course_ids=("ECE 391",)),
        EvalCase(query="q2", expected_course_ids=("ECE 408",)),
    ]
    chunks = {
        "q1": [_chunk("ECE 391")],
        "q2": [_chunk("ECE 408")],
    }
    _patch_semantic(monkeypatch, chunks)

    report = evaluate(MagicMock(), MagicMock(), cases)

    assert isinstance(report, EvalReport)
    assert report.total == 2
    assert report.top1_hit_rate == 1.0
    assert report.topk_hit_rate == 1.0
    assert report.avg_top_similarity == pytest.approx(0.9)


def test_top1_miss_but_topk_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [EvalCase(query="q", expected_course_ids=("ECE 408",))]
    chunks = {
        "q": [
            _chunk("ECE 391"),  # top1 misses
            _chunk("ECE 408"),  # in topk
        ]
    }
    _patch_semantic(monkeypatch, chunks)

    report = evaluate(MagicMock(), MagicMock(), cases)

    assert report.top1_hits == 0
    assert report.topk_hits == 1
    assert report.top1_hit_rate == 0.0
    assert report.topk_hit_rate == 1.0


def test_full_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [EvalCase(query="q", expected_course_ids=("ECE 999",))]
    chunks = {"q": [_chunk("ECE 391"), _chunk("ECE 408")]}
    _patch_semantic(monkeypatch, chunks)

    report = evaluate(MagicMock(), MagicMock(), cases)

    assert report.top1_hits == 0
    assert report.topk_hits == 0


def test_no_results_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [EvalCase(query="q", expected_course_ids=("ECE 391",))]
    _patch_semantic(monkeypatch, {"q": []})

    report = evaluate(MagicMock(), MagicMock(), cases)

    assert report.top1_hits == 0
    assert report.topk_hits == 0
    assert report.avg_top_similarity == 0.0
    assert report.cases[0].top_similarity == 0.0


def test_section_type_hit_requires_course_and_section_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = [
        EvalCase(
            query="right_section",
            expected_course_ids=("ECE 391",),
            expected_section_type="prerequisites",
        ),
        EvalCase(
            query="wrong_section",
            expected_course_ids=("ECE 391",),
            expected_section_type="prerequisites",
        ),
        EvalCase(
            query="wrong_course",
            expected_course_ids=("ECE 391",),
            expected_section_type="prerequisites",
        ),
    ]
    _patch_semantic(
        monkeypatch,
        {
            "right_section": [_chunk("ECE 391", "prerequisites")],
            "wrong_section": [_chunk("ECE 391", "overview")],
            "wrong_course": [_chunk("ECE 408", "prerequisites")],
        },
    )

    report = evaluate(MagicMock(), MagicMock(), cases)

    assert report.section_type_expected == 3
    assert report.section_type_hits == 1
    assert report.cases[0].section_type_hit is True
    assert report.cases[1].section_type_hit is False
    assert report.cases[2].section_type_hit is False


def test_section_type_not_counted_when_case_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = [EvalCase(query="q", expected_course_ids=("ECE 391",))]
    _patch_semantic(monkeypatch, {"q": [_chunk("ECE 391", "overview")]})

    report = evaluate(MagicMock(), MagicMock(), cases)

    assert report.section_type_expected == 0
    assert report.section_type_hits == 0
    assert report.section_type_hit_rate == 0.0
    assert report.cases[0].section_type_hit is None


def test_empty_case_list_gives_zero_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_semantic(monkeypatch, {})
    report = evaluate(MagicMock(), MagicMock(), [])

    assert report.total == 0
    assert report.top1_hit_rate == 0.0
    assert report.topk_hit_rate == 0.0
    assert report.avg_top_similarity == 0.0


def test_format_report_contains_summary_and_per_case_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = [
        EvalCase(
            query="What is ECE 391?",
            expected_course_ids=("ECE 391",),
            expected_section_type="overview",
        ),
        EvalCase(query="miss", expected_course_ids=("ECE 999",)),
    ]
    _patch_semantic(
        monkeypatch,
        {
            "What is ECE 391?": [_chunk("ECE 391", "overview", 0.87)],
            "miss": [_chunk("ECE 391", "overview", 0.4)],
        },
    )

    report = evaluate(MagicMock(), MagicMock(), cases)
    text = format_report(report)

    assert "top1=50%" in text
    assert "ECE 391" in text
    assert "sim=0.87" in text
    # Hit marker for the first case, miss marker for the second.
    assert "✓" in text
    assert "✗" in text
