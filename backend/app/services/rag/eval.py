"""Versioned, retrieval-only evaluation for the course RAG pipeline.

This module deliberately evaluates evidence retrieval rather than generated
answers.  A frozen JSON case set supplies the labels; a small retriever adapter
lets the same rubric compare semantic pgvector search with the keyword
baseline without a live database in unit tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Protocol

from sqlalchemy.orm import Session

from app.services.rag.embeddings import EmbeddingClient
from app.services.rag.pgvector_retriever import LOW_CONFIDENCE_THRESHOLD, semantic_search
from app.services.rag.normalize import extract_course_ids
from app.services.rag.retriever import RetrievedChunk, search_course_chunks_by_keyword


RetrievalMode = Literal["semantic", "keyword"]
SafetyExpectation = Literal["evidence", "low_confidence_or_no_evidence", "no_evidence"]


@dataclass(frozen=True)
class EvalCase:
    """One frozen retrieval label.

    Empty ``expected_course_ids`` is valid only for an unsupported question.
    Those cases do not enter Recall@k's denominator; they test that retrieval
    returns no evidence or an explicitly low-confidence result instead.
    """

    query: str
    expected_course_ids: tuple[str, ...]
    expected_section_type: str | None = None
    note: str | None = None
    case_id: str = ""
    category: str = "direct_lookup"
    expected_source_name: str | None = None
    expected_safety: SafetyExpectation = "evidence"


@dataclass(frozen=True)
class RetrievalResponse:
    """Retriever-adapter output kept intentionally independent of SQLAlchemy."""

    chunks: list[RetrievedChunk]
    mode: RetrievalMode
    applied_course_ids: tuple[str, ...] = ()
    low_confidence_threshold: float | None = None


class RetrievalAdapter(Protocol):
    def __call__(self, case: EvalCase, top_k: int) -> RetrievalResponse | list[RetrievedChunk]: ...


@dataclass
class EvalCaseResult:
    case: EvalCase
    top_chunks: list[RetrievedChunk]
    top1_hit: bool | None
    topk_hit: bool | None
    section_type_hit: bool | None
    source_hit: bool | None
    safety_hit: bool | None
    observed_safety: str
    applied_course_ids: tuple[str, ...]
    top_similarity: float


@dataclass
class EvalReport:
    case_set_id: str
    retrieval_mode: RetrievalMode
    top_k: int
    total: int
    evidence_expected: int
    top1_hits: int
    topk_hits: int
    unfiltered_evidence_expected: int
    unfiltered_top1_hits: int
    unfiltered_topk_hits: int
    section_type_expected: int
    section_type_hits: int
    source_expected: int
    source_hits: int
    safety_expected: int
    safety_hits: int
    avg_top_similarity: float
    cases: list[EvalCaseResult] = field(default_factory=list)

    @property
    def top1_hit_rate(self) -> float:
        return self.top1_hits / self.evidence_expected if self.evidence_expected else 0.0

    @property
    def topk_hit_rate(self) -> float:
        return self.topk_hits / self.evidence_expected if self.evidence_expected else 0.0

    @property
    def unfiltered_top1_hit_rate(self) -> float:
        return (
            self.unfiltered_top1_hits / self.unfiltered_evidence_expected
            if self.unfiltered_evidence_expected
            else 0.0
        )

    @property
    def unfiltered_topk_hit_rate(self) -> float:
        return (
            self.unfiltered_topk_hits / self.unfiltered_evidence_expected
            if self.unfiltered_evidence_expected
            else 0.0
        )

    @property
    def section_type_hit_rate(self) -> float:
        return self.section_type_hits / self.section_type_expected if self.section_type_expected else 0.0

    @property
    def source_hit_rate(self) -> float:
        return self.source_hits / self.source_expected if self.source_expected else 0.0

    @property
    def safety_hit_rate(self) -> float:
        return self.safety_hits / self.safety_expected if self.safety_expected else 0.0


def default_cases_path() -> Path:
    """Return the repository-owned, frozen v1 case set."""
    return Path(__file__).resolve().parents[3] / "evaluation" / "retrieval_cases.v1.json"


def load_cases(path: str | Path = default_cases_path()) -> tuple[str, tuple[EvalCase, ...]]:
    """Load and validate a versioned retrieval-case JSON file.

    The loader is public so a reviewer or test can use a candidate case file
    without changing application code.  It fails early on labels that would
    make the metrics ambiguous.
    """
    case_path = Path(path)
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    case_set_id = payload.get("case_set_id")
    if not isinstance(case_set_id, str) or not case_set_id:
        raise ValueError("case file requires a non-empty case_set_id")
    if payload.get("schema_version") != 1:
        raise ValueError("case file schema_version must be 1")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("case file requires a non-empty cases list")

    case_ids: set[str] = set()
    cases: list[EvalCase] = []
    valid_safety = {"evidence", "low_confidence_or_no_evidence", "no_evidence"}
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("each retrieval case must be an object")
        case_id = raw.get("id")
        query = raw.get("query")
        course_ids = raw.get("acceptable_course_ids")
        expected_safety = raw.get("expected_safety", "evidence")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("each retrieval case requires a non-empty id")
        if case_id in case_ids:
            raise ValueError(f"duplicate retrieval case id: {case_id}")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"case {case_id} requires a non-empty query")
        if not isinstance(course_ids, list) or not all(isinstance(item, str) and item for item in course_ids):
            raise ValueError(f"case {case_id} acceptable_course_ids must be a list of non-empty strings")
        if expected_safety not in valid_safety:
            raise ValueError(f"case {case_id} has unsupported expected_safety: {expected_safety}")
        if course_ids and expected_safety != "evidence":
            raise ValueError(f"case {case_id} has evidence labels but non-evidence safety expectation")
        if not course_ids and expected_safety == "evidence":
            raise ValueError(f"case {case_id} has no evidence labels but expects evidence")

        section = raw.get("expected_section_type")
        source = raw.get("expected_source_name")
        for value, field_name in ((section, "expected_section_type"), (source, "expected_source_name")):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"case {case_id} {field_name} must be a non-empty string when present")
        if not course_ids and (section is not None or source is not None):
            raise ValueError(f"case {case_id} cannot expect section/source without evidence")

        cases.append(
            EvalCase(
                case_id=case_id,
                query=query,
                expected_course_ids=tuple(course_ids),
                expected_section_type=section,
                expected_source_name=source,
                expected_safety=expected_safety,
                category=str(raw.get("category", "direct_lookup")),
                note=raw.get("note"),
            )
        )
        case_ids.add(case_id)
    return case_set_id, tuple(cases)


# Compatibility for callers of the former in-code fixture. New code should use
# ``load_cases`` so its case-set version is recorded in an artifact manifest.
CORE_GOLDEN_SET_ID, CORE_GOLDEN_SET = load_cases()


def build_retriever(
    mode: RetrievalMode,
    session: Session,
    embedding_client: EmbeddingClient,
) -> RetrievalAdapter:
    """Create an explicit semantic or keyword adapter for fair comparison."""
    if mode == "semantic":
        return lambda case, top_k: RetrievalResponse(
            chunks=semantic_search(
                session,
                case.query,
                embedding_client,
                course_ids=course_filter_for_case(case),
                top_k=top_k,
            ),
            mode="semantic",
            applied_course_ids=tuple(course_filter_for_case(case) or ()),
            low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD,
        )
    if mode == "keyword":
        return lambda case, top_k: RetrievalResponse(
            chunks=search_course_chunks_by_keyword(
                session,
                case.query,
                course_ids=course_filter_for_case(case),
                top_k=top_k,
            ),
            mode="keyword",
            applied_course_ids=tuple(course_filter_for_case(case) or ()),
            # Lexical overlap is not calibrated against cosine similarity.
            low_confidence_threshold=None,
        )
    raise ValueError(f"unsupported retrieval mode: {mode}")


def course_filter_for_case(case: EvalCase) -> list[str] | None:
    """Mirror the chat router's course-ID metadata filter in retrieval eval.

    Course QA and prerequisite cases pass explicitly mentioned course IDs to
    ``search_course_docs``. An unsupported query with an invented course ID
    follows the same path and must receive no unrelated catalog evidence.
    Paraphrase and cross-course discovery cases remain unfiltered, because
    their intended behavior is semantic discovery rather than direct lookup.
    """
    if case.category not in {"direct_lookup", "metadata_filtered", "unsupported"}:
        return None
    return extract_course_ids(case.query) or None


def evaluate(
    session: Session,
    embedding_client: EmbeddingClient,
    cases: Iterable[EvalCase] = CORE_GOLDEN_SET,
    *,
    top_k: int = 3,
    mode: RetrievalMode = "semantic",
    retriever: RetrievalAdapter | None = None,
    case_set_id: str = CORE_GOLDEN_SET_ID,
) -> EvalReport:
    """Score a retriever against frozen labels without requiring live Postgres in tests."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    case_list = list(cases)
    active_retriever = retriever or build_retriever(mode, session, embedding_client)
    results: list[EvalCaseResult] = []
    evidence_expected = top1_hits = topk_hits = 0
    unfiltered_evidence_expected = unfiltered_top1_hits = unfiltered_topk_hits = 0
    section_type_expected = section_type_hits = 0
    source_expected = source_hits = 0
    safety_expected = safety_hits = 0
    similarity_sum = 0.0

    for case in case_list:
        response = active_retriever(case, top_k)
        chunks = response.chunks if isinstance(response, RetrievalResponse) else response
        applied_course_ids = response.applied_course_ids if isinstance(response, RetrievalResponse) else ()
        top_chunk = chunks[0] if chunks else None
        top_similarity = top_chunk.score if top_chunk else 0.0
        similarity_sum += top_similarity
        confidence_threshold = (
            response.low_confidence_threshold
            if isinstance(response, RetrievalResponse)
            else LOW_CONFIDENCE_THRESHOLD
        )
        observed_safety = _observed_safety(chunks, confidence_threshold)

        top1_hit: bool | None = None
        topk_hit: bool | None = None
        if case.expected_course_ids:
            evidence_expected += 1
            top1_hit = bool(top_chunk and top_chunk.course_id in case.expected_course_ids)
            topk_hit = any(chunk.course_id in case.expected_course_ids for chunk in chunks)
            top1_hits += int(top1_hit)
            topk_hits += int(topk_hit)
            if not course_filter_for_case(case):
                unfiltered_evidence_expected += 1
                unfiltered_top1_hits += int(top1_hit)
                unfiltered_topk_hits += int(topk_hit)

        section_type_hit: bool | None = None
        if case.expected_section_type is not None:
            section_type_expected += 1
            section_type_hit = bool(
                top_chunk
                and top_chunk.course_id in case.expected_course_ids
                and top_chunk.section_type == case.expected_section_type
            )
            section_type_hits += int(section_type_hit)

        source_hit: bool | None = None
        if case.expected_source_name is not None:
            source_expected += 1
            source_hit = bool(
                top_chunk
                and top_chunk.course_id in case.expected_course_ids
                and top_chunk.source_name == case.expected_source_name
            )
            source_hits += int(source_hit)

        safety_hit: bool | None = None
        if case.expected_safety != "evidence":
            safety_expected += 1
            safety_hit = (
                observed_safety == "no_evidence"
                if case.expected_safety == "no_evidence"
                else observed_safety in {"low_confidence", "no_evidence"}
            )
            safety_hits += int(safety_hit)

        results.append(
            EvalCaseResult(
                case=case,
                top_chunks=chunks,
                top1_hit=top1_hit,
                topk_hit=topk_hit,
                section_type_hit=section_type_hit,
                source_hit=source_hit,
                safety_hit=safety_hit,
                observed_safety=observed_safety,
                applied_course_ids=applied_course_ids,
                top_similarity=top_similarity,
            )
        )

    total = len(case_list)
    return EvalReport(
        case_set_id=case_set_id,
        retrieval_mode=mode,
        top_k=top_k,
        total=total,
        evidence_expected=evidence_expected,
        top1_hits=top1_hits,
        topk_hits=topk_hits,
        unfiltered_evidence_expected=unfiltered_evidence_expected,
        unfiltered_top1_hits=unfiltered_top1_hits,
        unfiltered_topk_hits=unfiltered_topk_hits,
        section_type_expected=section_type_expected,
        section_type_hits=section_type_hits,
        source_expected=source_expected,
        source_hits=source_hits,
        safety_expected=safety_expected,
        safety_hits=safety_hits,
        avg_top_similarity=similarity_sum / total if total else 0.0,
        cases=results,
    )


def _observed_safety(
    chunks: list[RetrievedChunk], confidence_threshold: float | None
) -> str:
    if not chunks:
        return "no_evidence"
    if confidence_threshold is not None and chunks[0].score < confidence_threshold:
        return "low_confidence"
    return "evidence"


def format_report(report: EvalReport) -> str:
    """Human-readable summary suitable for stdout."""
    lines = [
        f"Retrieval eval {report.case_set_id} ({report.retrieval_mode}, k={report.top_k}): "
        f"Recall@1={report.top1_hit_rate:.0%} Recall@{report.top_k}={report.topk_hit_rate:.0%} "
        f"unfiltered Recall@{report.top_k}={report.unfiltered_topk_hit_rate:.0%} "
        f"source={report.source_hit_rate:.0%} section={report.section_type_hit_rate:.0%} "
        f"safety={report.safety_hit_rate:.0%}",
        "-" * 78,
    ]
    for result in report.cases:
        top_chunk = result.top_chunks[0] if result.top_chunks else None
        got = f"{top_chunk.course_id}/{top_chunk.section_type} sim={top_chunk.score:.2f}" if top_chunk else "(no results)"
        marker = "✓" if result.top1_hit else ("~" if result.topk_hit else "✗")
        lines.append(f"{marker} {result.case.case_id}: {result.case.query}\n    got: {got}")
    return "\n".join(lines)


__all__ = [
    "CORE_GOLDEN_SET",
    "CORE_GOLDEN_SET_ID",
    "EvalCase",
    "EvalCaseResult",
    "EvalReport",
    "RetrievalAdapter",
    "RetrievalMode",
    "RetrievalResponse",
    "build_retriever",
    "course_filter_for_case",
    "default_cases_path",
    "evaluate",
    "format_report",
    "load_cases",
]
