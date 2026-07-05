"""Golden Q&A evaluation for course retrieval.

Focused on retrieval quality (not answer generation): given a query, do we
put the right course chunk in the top-k? Section type is also tracked so we
can see whether the chunker's semantic decomposition is paying off — a
prerequisite question should hit a `prerequisites` chunk, not the overview.

The metric set is intentionally small so this can run in seconds on a live
ICRN box after ingestion. For deeper LLM-answer eval we'll layer another
pass on top later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy.orm import Session

from app.services.rag.embeddings import EmbeddingClient
from app.services.rag.pgvector_retriever import semantic_search
from app.services.rag.retriever import RetrievedChunk


@dataclass(frozen=True)
class EvalCase:
    """One golden retrieval question.

    ``expected_course_ids`` is a set of acceptable answers — some questions
    could reasonably retrieve either of two courses. ``expected_section_type``
    is optional; when set, we credit a section-type hit only if the top result
    matches.
    """

    query: str
    expected_course_ids: tuple[str, ...]
    expected_section_type: str | None = None
    note: str | None = None


@dataclass
class EvalCaseResult:
    case: EvalCase
    top_chunks: list[RetrievedChunk]
    top1_hit: bool
    topk_hit: bool
    section_type_hit: bool | None  # None when case has no expected section
    top_similarity: float


@dataclass
class EvalReport:
    total: int
    top1_hits: int
    topk_hits: int
    section_type_expected: int
    section_type_hits: int
    avg_top_similarity: float
    cases: list[EvalCaseResult] = field(default_factory=list)

    @property
    def top1_hit_rate(self) -> float:
        return self.top1_hits / self.total if self.total else 0.0

    @property
    def topk_hit_rate(self) -> float:
        return self.topk_hits / self.total if self.total else 0.0

    @property
    def section_type_hit_rate(self) -> float:
        if not self.section_type_expected:
            return 0.0
        return self.section_type_hits / self.section_type_expected


CORE_GOLDEN_SET: tuple[EvalCase, ...] = (
    EvalCase(
        query="What are the prerequisites for ECE 391?",
        expected_course_ids=("ECE 391",),
        expected_section_type="prerequisites",
        note="Direct prerequisite lookup, single-course.",
    ),
    EvalCase(
        query="Tell me about GPU programming and CUDA.",
        expected_course_ids=("ECE 408",),
        expected_section_type="overview",
        note="Semantic query; no course id mentioned.",
    ),
    EvalCase(
        query="Which course covers computer architecture and memory hierarchy?",
        expected_course_ids=("ECE 411", "CS 433"),
        expected_section_type="overview",
    ),
    EvalCase(
        query="Best course for someone targeting AI infrastructure roles?",
        expected_course_ids=("ECE 408", "ECE 411"),
        expected_section_type="career_direction",
    ),
    EvalCase(
        query="How many credit hours is ECE 385?",
        expected_course_ids=("ECE 385",),
        expected_section_type="credit_hours",
    ),
    EvalCase(
        query="What is ECE 448 about?",
        expected_course_ids=("ECE 448",),
        expected_section_type="overview",
    ),
    EvalCase(
        query="Systems programming, operating systems, and C.",
        expected_course_ids=("ECE 391",),
        expected_section_type="overview",
        note="Paraphrased overview; no course id.",
    ),
    EvalCase(
        query="Course focused on computer vision or robotics?",
        expected_course_ids=("ECE 470", "ECE 494"),
        expected_section_type="career_direction",
    ),
)


def evaluate(
    session: Session,
    embedding_client: EmbeddingClient,
    cases: Iterable[EvalCase] = CORE_GOLDEN_SET,
    *,
    top_k: int = 3,
) -> EvalReport:
    """Run the golden set against the semantic retriever and score results."""
    case_list = list(cases)
    results: list[EvalCaseResult] = []
    top1_hits = 0
    topk_hits = 0
    section_type_expected = 0
    section_type_hits = 0
    similarity_sum = 0.0

    for case in case_list:
        chunks = semantic_search(
            session, case.query, embedding_client, top_k=top_k
        )
        top1 = chunks[0].course_id if chunks else None
        retrieved_ids = [c.course_id for c in chunks]
        top1_hit = top1 in case.expected_course_ids if top1 else False
        topk_hit = any(cid in case.expected_course_ids for cid in retrieved_ids)

        section_type_hit: bool | None = None
        if case.expected_section_type is not None:
            section_type_expected += 1
            if (
                chunks
                and chunks[0].course_id in case.expected_course_ids
                and chunks[0].section_type == case.expected_section_type
            ):
                section_type_hit = True
                section_type_hits += 1
            else:
                section_type_hit = False

        top_sim = chunks[0].score if chunks else 0.0
        similarity_sum += top_sim
        top1_hits += int(top1_hit)
        topk_hits += int(topk_hit)

        results.append(
            EvalCaseResult(
                case=case,
                top_chunks=chunks,
                top1_hit=top1_hit,
                topk_hit=topk_hit,
                section_type_hit=section_type_hit,
                top_similarity=top_sim,
            )
        )

    total = len(case_list)
    avg_sim = similarity_sum / total if total else 0.0

    return EvalReport(
        total=total,
        top1_hits=top1_hits,
        topk_hits=topk_hits,
        section_type_expected=section_type_expected,
        section_type_hits=section_type_hits,
        avg_top_similarity=avg_sim,
        cases=results,
    )


def format_report(report: EvalReport) -> str:
    """Human-readable summary suitable for stdout."""
    lines: list[str] = []
    lines.append(
        f"Retrieval eval: {report.total} cases | "
        f"top1={report.top1_hit_rate:.0%} "
        f"topk={report.topk_hit_rate:.0%} "
        f"section={report.section_type_hit_rate:.0%} "
        f"avg_sim={report.avg_top_similarity:.2f}"
    )
    lines.append("-" * 78)
    for i, res in enumerate(report.cases, start=1):
        marker = "✓" if res.top1_hit else ("~" if res.topk_hit else "✗")
        top_chunk = res.top_chunks[0] if res.top_chunks else None
        got = (
            f"{top_chunk.course_id}/{top_chunk.section_type} sim={top_chunk.score:.2f}"
            if top_chunk
            else "(no results)"
        )
        expected = "|".join(res.case.expected_course_ids)
        if res.case.expected_section_type:
            expected += f" [{res.case.expected_section_type}]"
        lines.append(
            f"{marker} case {i}: {res.case.query}\n"
            f"    expected: {expected}\n"
            f"    got:      {got}"
        )
    return "\n".join(lines)


__all__ = [
    "EvalCase",
    "EvalCaseResult",
    "EvalReport",
    "CORE_GOLDEN_SET",
    "evaluate",
    "format_report",
]
