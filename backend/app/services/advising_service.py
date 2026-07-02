from time import perf_counter
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    CompareRequest,
    CompareResponse,
    CourseSummary,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
)
from app.services.answer_synthesis import build_answer
from app.services.llm import LLMClient, create_llm_client
from app.services.rag.citation import citation_from_chunk
from app.services.rag.retriever import (
    RetrievedChunk,
    search_course_docs,
    search_course_docs_from_db,
)
from app.services.tools.dispatcher import DispatchedResults, execute_plan
from app.services.tools.router import plan_tools
from app.services.tools.schemas import RetrievedDoc
from app.services.tools.trace import ToolTraceCollector


async def build_chat_response(
    request: ChatRequest,
    db_session: Session,
    llm_client: LLMClient | None = None,
) -> ChatResponse:
    """End-to-end chat pipeline: router → dispatcher → LLM synthesis.

    ``llm_client`` is injectable for tests. Production callers pass nothing;
    the factory reads ``LLM_BACKEND`` from env and returns the right backend.
    """
    start = perf_counter()
    collector = ToolTraceCollector()
    client = llm_client or create_llm_client()

    plan = plan_tools(request.message)
    results = execute_plan(db_session, plan, collector)

    citations = _citations_from_results(results)
    answer = await build_answer(
        plan.intent, request.message, results, client, collector
    )
    latency_ms = int((perf_counter() - start) * 1000)

    return ChatResponse(
        answer=answer,
        citations=citations,
        used_tools=collector.tool_names(),
        debug_trace=collector.to_debug_trace() if request.debug else None,
        latency_ms=latency_ms,
    )


def _citations_from_results(results: DispatchedResults) -> list[Citation]:
    if results.search_result is None:
        return []
    return [_citation_from_doc(doc) for doc in results.search_result.docs]


def _citation_from_doc(doc: RetrievedDoc) -> Citation:
    return Citation(
        source_name=doc.source_name,
        source_url=doc.source_url,
        course_id=doc.course_id,
        snippet=doc.snippet,
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


def _search_docs(
    query: str,
    *,
    db_session: Session | None,
    course_ids: list[str] | None = None,
    top_k: int = 5,
) -> Sequence[RetrievedChunk]:
    if db_session is not None:
        return search_course_docs_from_db(
            db_session,
            query,
            course_ids=course_ids,
            top_k=top_k,
        )
    return search_course_docs(query, course_ids=course_ids, top_k=top_k)
