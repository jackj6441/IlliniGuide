import json
from collections.abc import AsyncIterator, Sequence
from time import perf_counter

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
from app.services.answer_synthesis import build_answer, stream_answer
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


async def build_chat_response_stream(
    request: ChatRequest,
    db_session: Session,
    llm_client: LLMClient | None = None,
) -> AsyncIterator[str]:
    """Yield the chat response as Server-Sent Events (SSE) strings.

    Event schema (each line ends with ``\\n\\n`` per the SSE spec):

    - ``data: {"type": "content", "delta": "..."}`` — a text chunk from
      the LLM. Emitted 0..N times.
    - ``data: {"type": "metadata", "citations": [...], "used_tools": [...],
      "latency_ms": 123, "debug_trace": {...}?}`` — emitted once, after
      the LLM stream finishes; ``debug_trace`` is included only when
      ``request.debug`` is true.
    - ``data: [DONE]`` — end-of-stream marker.

    The tools stage runs synchronously *before* streaming starts, so
    citations and (mostly) the used-tools list are known at the point
    where content starts flowing; they are still delivered in the final
    ``metadata`` event because the ``llm_generate_stream`` trace entry is
    only finalized after the stream ends.
    """
    start = perf_counter()
    collector = ToolTraceCollector()
    client = llm_client or create_llm_client()

    plan = plan_tools(request.message)
    results = execute_plan(db_session, plan, collector)
    citations = _citations_from_results(results)

    async for chunk in stream_answer(
        plan.intent, request.message, results, client, collector
    ):
        yield _sse_event({"type": "content", "delta": chunk})

    latency_ms = int((perf_counter() - start) * 1000)
    metadata: dict = {
        "type": "metadata",
        "citations": [citation.model_dump() for citation in citations],
        "used_tools": collector.tool_names(),
        "latency_ms": latency_ms,
    }
    if request.debug:
        metadata["debug_trace"] = collector.to_debug_trace().model_dump()

    yield _sse_event(metadata)
    yield "data: [DONE]\n\n"


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


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
