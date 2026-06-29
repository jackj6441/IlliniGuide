from time import perf_counter

from app.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    CompareRequest,
    CompareResponse,
    CourseSummary,
    DebugTrace,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
)


MOCK_CITATION = Citation(
    source_name="Mock Course Dataset",
    source_url="https://example.com/illiniguideserve/mock-course-data",
    course_id="ECE 391",
    snippet="Mock evidence placeholder. TODO: replace with real retrieved course evidence in Version 1 RAG.",
)


def build_mock_chat_response(request: ChatRequest) -> ChatResponse:
    start = perf_counter()
    used_tools = ["mock_intent_detector", "mock_course_retriever"]
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
                    "course_id": "ECE 391",
                    "source_name": MOCK_CITATION.source_name,
                    "snippet": MOCK_CITATION.snippet,
                }
            ],
            recommendation_scores=[],
        )

    latency_ms = int((perf_counter() - start) * 1000)
    return ChatResponse(
        answer=(
            "This is a mocked advising response. TODO: replace this with RAG + tool-orchestrated "
            "answer generation in Version 1."
        ),
        citations=[MOCK_CITATION],
        used_tools=used_tools,
        debug_trace=debug_trace,
        latency_ms=latency_ms,
    )


def build_mock_compare_response(request: CompareRequest) -> CompareResponse:
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
        citations=[MOCK_CITATION],
    )


def build_mock_recommend_response(request: RecommendRequest) -> RecommendResponse:
    recommendation = Recommendation(
        course_id="ECE 408",
        title="Applied Parallel Programming",
        reason=(
            "Mock recommendation for the requested direction. TODO: replace with direction_match, "
            "prerequisite_readiness, GPA risk, and course progression scoring."
        ),
        citations=[MOCK_CITATION],
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
