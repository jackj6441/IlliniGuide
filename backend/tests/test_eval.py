"""Retrieval-eval tests use adapters, not a live pgvector database."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.rag.eval import (
    EvalCase,
    RetrievalResponse,
    build_retriever,
    course_filter_for_case,
    evaluate,
    format_report,
    load_cases,
)
from app.services.rag.retriever import RetrievedChunk
from scripts.eval_retrieval import (
    describe_ingestion_manifest,
    serialize_report,
    validate_manifest_matches_corpus,
    write_artifacts,
)


def _chunk(
    course_id: str,
    section_type: str = "overview",
    score: float = 0.9,
    source_name: str = "UIUC Course Catalog",
) -> RetrievedChunk:
    return RetrievedChunk(
        course_id=course_id,
        source_name=source_name,
        source_url=f"https://courses.illinois.edu/{course_id.replace(' ', '')}",
        section_type=section_type,
        chunk_text=f"{course_id} content",
        score=score,
    )


def _adapter(chunks_by_query: dict[str, list[RetrievedChunk]], mode: str = "semantic"):
    return lambda case, top_k: RetrievalResponse(
        chunks_by_query.get(case.query, []),
        mode=mode,  # type: ignore[arg-type]
        low_confidence_threshold=0.35 if mode == "semantic" else None,
    )


def test_load_default_case_file_is_frozen_and_has_required_coverage() -> None:
    case_set_id, cases = load_cases()

    assert case_set_id == "retrieval_cases.v1"
    assert 30 <= len(cases) <= 50
    assert {case.category for case in cases} >= {
        "direct_lookup",
        "paraphrase",
        "cross_course",
        "metadata_filtered",
        "unsupported",
    }
    assert any(case.expected_section_type for case in cases)
    assert any(case.expected_source_name for case in cases)
    assert any(case.expected_safety != "evidence" for case in cases)


def test_case_loader_rejects_ambiguous_unsupported_labels(tmp_path: Path) -> None:
    case_file = tmp_path / "bad.json"
    case_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "case_set_id": "bad.v1",
                "cases": [
                    {
                        "id": "unsupported",
                        "query": "unknown query",
                        "acceptable_course_ids": [],
                        "expected_safety": "evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no evidence labels"):
        load_cases(case_file)


def test_evaluate_scores_recall_source_and_section_separately() -> None:
    cases = [
        EvalCase(
            case_id="right",
            query="right",
            expected_course_ids=("ECE 391",),
            expected_section_type="prerequisites",
            expected_source_name="UIUC Course Catalog",
        ),
        EvalCase(
            case_id="topk-only",
            query="topk-only",
            expected_course_ids=("ECE 408",),
            expected_source_name="UIUC Course Catalog",
        ),
    ]
    report = evaluate(
        MagicMock(),
        MagicMock(),
        cases,
        top_k=3,
        retriever=_adapter(
            {
                "right": [_chunk("ECE 391", "prerequisites")],
                "topk-only": [_chunk("ECE 391"), _chunk("ECE 408")],
            }
        ),
        case_set_id="fixture.v1",
    )

    assert report.top1_hits == 1
    assert report.topk_hits == 2
    assert report.top1_hit_rate == 0.5
    assert report.topk_hit_rate == 1.0
    assert report.unfiltered_top1_hit_rate == 0.5
    assert report.unfiltered_topk_hit_rate == 1.0
    assert report.section_type_hit_rate == 1.0
    assert report.source_hit_rate == 0.5


def test_evaluate_scores_unsupported_query_safety_without_polluting_recall() -> None:
    cases = [
        EvalCase(
            case_id="supported",
            query="supported",
            expected_course_ids=("ECE 391",),
        ),
        EvalCase(
            case_id="unsupported",
            query="unsupported",
            expected_course_ids=(),
            expected_safety="low_confidence_or_no_evidence",
        ),
        EvalCase(
            case_id="invented",
            query="invented",
            expected_course_ids=(),
            expected_safety="no_evidence",
        ),
    ]
    report = evaluate(
        MagicMock(),
        MagicMock(),
        cases,
        retriever=_adapter(
            {
                "supported": [_chunk("ECE 391")],
                "unsupported": [_chunk("ECE 408", score=0.1)],
                "invented": [],
            }
        ),
    )

    assert report.evidence_expected == 1
    assert report.top1_hit_rate == 1.0
    assert report.safety_expected == 2
    assert report.safety_hits == 2
    assert report.safety_hit_rate == 1.0
    assert report.cases[1].observed_safety == "low_confidence"
    assert report.cases[2].observed_safety == "no_evidence"


def test_evaluate_accepts_a_plain_list_stub_for_simple_tdd() -> None:
    case = EvalCase(case_id="plain", query="plain", expected_course_ids=("ECE 391",))
    report = evaluate(
        MagicMock(),
        MagicMock(),
        [case],
        retriever=lambda case, top_k: [_chunk("ECE 391")],
    )

    assert report.top1_hit_rate == 1.0


def test_explicit_keyword_and_semantic_adapters_are_stub_testable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.rag.eval as eval_module

    monkeypatch.setattr(
        eval_module,
        "semantic_search",
        lambda session, query, client, course_ids, top_k: [_chunk("ECE 408")],
    )
    monkeypatch.setattr(
        eval_module,
        "search_course_chunks_by_keyword",
        lambda session, query, course_ids, top_k: [_chunk("ECE 391")],
    )

    case = EvalCase(
        case_id="filtered",
        category="metadata_filtered",
        query="What are prerequisites for ECE 391?",
        expected_course_ids=("ECE 391",),
    )
    semantic = build_retriever("semantic", MagicMock(), MagicMock())(case, 3)
    keyword = build_retriever("keyword", MagicMock(), MagicMock())(case, 3)

    assert semantic.mode == "semantic"
    assert semantic.chunks[0].course_id == "ECE 408"
    assert semantic.applied_course_ids == ("ECE 391",)
    assert keyword.mode == "keyword"
    assert keyword.chunks[0].course_id == "ECE 391"
    assert keyword.applied_course_ids == ("ECE 391",)


def test_course_id_filter_matches_course_qa_and_unsupported_query_paths() -> None:
    direct_lookup = EvalCase(
        case_id="direct",
        category="direct_lookup",
        query="What is ECE 391?",
        expected_course_ids=("ECE 391",),
    )
    filtered = EvalCase(
        case_id="filtered",
        category="metadata_filtered",
        query="Prerequisites for ECE 391",
        expected_course_ids=("ECE 391",),
    )
    discovery = EvalCase(
        case_id="discovery",
        category="cross_course",
        query="Compare ECE 391 and ECE 408",
        expected_course_ids=("ECE 391", "ECE 408"),
    )
    invented = EvalCase(
        case_id="invented",
        category="unsupported",
        query="Tell me about ECE 999",
        expected_course_ids=(),
        expected_safety="no_evidence",
    )

    assert course_filter_for_case(direct_lookup) == ["ECE 391"]
    assert course_filter_for_case(filtered) == ["ECE 391"]
    assert course_filter_for_case(discovery) is None
    assert course_filter_for_case(invented) == ["ECE 999"]


def test_course_id_filtered_cases_are_excluded_from_unfiltered_recall() -> None:
    cases = [
        EvalCase(
            case_id="direct",
            category="direct_lookup",
            query="What is ECE 391?",
            expected_course_ids=("ECE 391",),
        ),
        EvalCase(
            case_id="filtered",
            category="metadata_filtered",
            query="ECE 391 prerequisites",
            expected_course_ids=("ECE 391",),
        ),
        EvalCase(
            case_id="discovery",
            category="paraphrase",
            query="systems programming",
            expected_course_ids=("ECE 391",),
        ),
    ]
    report = evaluate(
        MagicMock(),
        MagicMock(),
        cases,
        retriever=_adapter(
            {
                "What is ECE 391?": [_chunk("ECE 391")],
                "ECE 391 prerequisites": [_chunk("ECE 391")],
                "systems programming": [_chunk("ECE 408")],
            }
        ),
    )

    assert report.topk_hit_rate == 2 / 3
    assert report.unfiltered_evidence_expected == 1
    assert report.unfiltered_topk_hit_rate == 0.0


def test_evaluate_rejects_non_positive_top_k() -> None:
    with pytest.raises(ValueError, match="positive"):
        evaluate(MagicMock(), MagicMock(), [], top_k=0, retriever=_adapter({}))


def test_format_report_includes_metric_names_and_case_id() -> None:
    report = evaluate(
        MagicMock(),
        MagicMock(),
        [EvalCase(case_id="case-a", query="q", expected_course_ids=("ECE 391",))],
        retriever=_adapter({"q": [_chunk("ECE 391")]}),
    )

    text = format_report(report)
    assert "Recall@1=100%" in text
    assert "source=0%" in text
    assert "case-a" in text


def test_cli_serialization_and_artifact_manifest_are_reproducible(tmp_path: Path) -> None:
    report = evaluate(
        MagicMock(),
        MagicMock(),
        [
            EvalCase(
                case_id="serialized",
                query="q",
                expected_course_ids=("ECE 391",),
                expected_source_name="UIUC Course Catalog",
            )
        ],
        retriever=_adapter({"q": [_chunk("ECE 391")]}),
        case_set_id="fixture.v1",
    )
    per_query, aggregate = serialize_report(report)
    assert per_query[0]["expected"]["acceptable_course_ids"] == ["ECE 391"]
    assert per_query[0]["observed"]["applied_course_ids"] == []
    assert aggregate["rates"]["recall_at_3"] == 1.0
    assert aggregate["rates"]["unfiltered_recall_at_3"] == 1.0

    now = datetime(2026, 7, 13, tzinfo=UTC)
    run_dir = write_artifacts(
        report,
        output_dir=tmp_path,
        run_id="20260713T000000Z-testsha",
        command=["python", "-m", "scripts.eval_retrieval"],
        case_file=Path("backend/evaluation/retrieval_cases.v1.json"),
        embedding_backend="stub",
        embedding_model="stub-model",
        embedding_dimension=384,
        started_at=now,
        finished_at=now,
        corpus_snapshot={"distinct_course_count": 155, "course_chunk_count": 620, "source_urls": ["https://example.com"]},
        ingestion_manifest={"run_id": "catalog-run", "sha256": "abc"},
        git_sha="testsha",
    )

    assert json.loads((run_dir / "per_query_results.json").read_text())[0]["case_id"] == "serialized"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["case_set"]["id"] == "fixture.v1"
    assert manifest["embedding"]["dimension"] == 384
    assert manifest["corpus"]["distinct_course_count"] == 155
    assert manifest["ingestion_manifest"]["run_id"] == "catalog-run"
    with pytest.raises(FileExistsError):
        write_artifacts(
            report,
            output_dir=tmp_path,
            run_id="20260713T000000Z-testsha",
            command=[],
            case_file=Path("cases.json"),
            embedding_backend="stub",
            embedding_model="stub",
            embedding_dimension=1,
            started_at=now,
            finished_at=now,
        )
    with pytest.raises(ValueError, match="single directory name"):
        write_artifacts(
            report,
            output_dir=tmp_path,
            run_id="../outside-artifacts",
            command=[],
            case_file=Path("cases.json"),
            embedding_backend="stub",
            embedding_model="stub",
            embedding_dimension=1,
            started_at=now,
            finished_at=now,
        )


def test_ingestion_manifest_description_records_checksum(tmp_path: Path) -> None:
    manifest_path = tmp_path / "ingestion.json"
    manifest_path.write_text(
        json.dumps({"run_id": "catalog-run", "total_distinct_course_count": 155}),
        encoding="utf-8",
    )

    description = describe_ingestion_manifest(manifest_path)

    assert description is not None
    assert description["run_id"] == "catalog-run"
    assert description["total_distinct_course_count"] == 155
    assert len(description["sha256"]) == 64


def test_ingestion_manifest_must_match_active_corpus() -> None:
    manifest = {
        "total_distinct_course_count": 155,
        "source_urls": ["https://catalog.example/cs", "https://ece.example/courses"],
    }
    corpus = {
        "distinct_course_count": 155,
        "source_urls": ["https://catalog.example/cs", "https://ece.example/courses"],
    }

    validate_manifest_matches_corpus(manifest, corpus)

    with pytest.raises(ValueError, match="course count"):
        validate_manifest_matches_corpus(manifest, {**corpus, "distinct_course_count": 154})
    with pytest.raises(ValueError, match="source URLs"):
        validate_manifest_matches_corpus(manifest, {**corpus, "source_urls": []})
