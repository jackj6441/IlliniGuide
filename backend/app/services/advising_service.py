from time import perf_counter
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.schemas import (
    ChatRequest,
    ChatResponse,
    CompareRequest,
    CompareResponse,
    CourseSummary,
    DebugTrace,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
)
from app.services.rag.citation import citation_from_chunk
from app.services.rag.retriever import (
    RetrievedChunk,
    search_course_docs,
    search_course_docs_from_db,
)


def build_mock_chat_response(
    request: ChatRequest,
    db_session: Session | None = None,
) -> ChatResponse:
    start = perf_counter()
    retrieved_chunks = _search_docs(request.message, db_session=db_session, top_k=5)
    citations = [citation_from_chunk(chunk) for chunk in retrieved_chunks]
    used_tools = ["mock_intent_detector", _retriever_name(db_session)]
    debug_trace = None

    if request.debug:
        debug_trace = DebugTrace(
            intent="course_qa",
            tool_calls=[
                {
                    "tool_name": "mock_course_retriever",
                    "status": "mocked",
                    "input": {"query": request.message},
                }
            ],
            retrieved_chunks=[
                {
                    "course_id": chunk.course_id,
                    "source_name": chunk.source_name,
                    "section_type": chunk.section_type,
                    "score": chunk.score,
                    "snippet": chunk.chunk_text,
                }
                for chunk in retrieved_chunks
            ],
            recommendation_scores=[],
        )

    latency_ms = int((perf_counter() - start) * 1000)
    return ChatResponse(
        answer=_build_grounded_mock_answer(retrieved_chunks),
        citations=citations,
        used_tools=used_tools,
        debug_trace=debug_trace,
        latency_ms=latency_ms,
    )


def build_mock_compare_response(
    request: CompareRequest,
    db_session: Session | None = None,
) -> CompareResponse:
    query = f"Compare {' '.join(request.course_ids)} {request.dimension or ''}".strip()
    retrieved_chunks = _search_docs(
        query,
        db_session=db_session,
        course_ids=request.course_ids,
        top_k=5,
    )
    citations = [citation_from_chunk(chunk) for chunk in retrieved_chunks]
    courses = [
        CourseSummary(
            course_id=course_id,
            title=f"Mock profile for {course_id}",
            notes=[
                "TODO: replace with structured course profile.",
                "TODO: add retrieved evidence and GPA/prerequisite signals.",
            ],
        )
        for course_id in request.course_ids
    ]
    return CompareResponse(
        summary=(
            "This is a mocked course comparison. TODO: replace with compare_courses tool output "
            "and citation-grounded synthesis."
        ),
        courses=courses,
        comparison={
            "dimension": request.dimension,
            "status": "mocked",
        },
        citations=citations,
    )


def build_mock_recommend_response(request: RecommendRequest) -> RecommendResponse:
    recommendation = Recommendation(
        course_id="ECE 408",
        title="Applied Parallel Programming",
        reason=(
            "Mock recommendation for the requested direction. TODO: replace with direction_match, "
            "prerequisite_readiness, GPA risk, and course progression scoring."
        ),
        citations=[],
    )
    debug_scores = None
    if request.debug:
        debug_scores = [
            {
                "course_id": recommendation.course_id,
                "score": 0.0,
                "status": "mocked",
                "target_direction": request.target_direction,
                "completed_courses": request.completed_courses,
            }
        ]
    return RecommendResponse(
        recommendations=[recommendation],
        debug_scores=debug_scores,
    )


def _build_grounded_mock_answer(retrieved_chunks: Sequence[RetrievedChunk]) -> str:
    if not retrieved_chunks:
        return (
            "I could not find enough evidence in the mock course dataset to answer this. "
            "TODO: replace this fallback with structured DB fallback and real RAG confidence checks."
        )

    course_ids = ", ".join(chunk.course_id for chunk in retrieved_chunks)
    evidence_summary = " ".join(chunk.chunk_text for chunk in retrieved_chunks[:2])
    return (
        f"Based on the mock retrieved evidence for {course_ids}: {evidence_summary} "
        "TODO: replace this template with LLM evidence synthesis in Version 1."
    )


def _search_docs(
    query: str,
    *,
    db_session: Session | None,
    course_ids: list[str] | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    if db_session is not None:
        return search_course_docs_from_db(
            db_session,
            query,
            course_ids=course_ids,
            top_k=top_k,
        )
    return search_course_docs(query, course_ids=course_ids, top_k=top_k)


def _retriever_name(db_session: Session | None) -> str:
    if db_session is not None:
        return "db_keyword_retriever"
    return "mock_keyword_retriever"
