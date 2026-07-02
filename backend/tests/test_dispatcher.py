from unittest.mock import patch

from app.services.tools.dispatcher import execute_plan
from app.services.tools.schemas import (
    CourseComparison,
    CourseComparisonItem,
    CourseProfile,
    CourseRecommendation,
    CourseRecommendations,
    GPAStats,
    PrerequisiteCheck,
    RetrievedDoc,
    SearchCourseDocsResult,
    ToolCall,
    ToolPlan,
)
from app.services.tools.trace import ToolTraceCollector


class DummySession:
    """Marker object; dispatcher passes it through, patched tools ignore it."""


def _plan(intent: str, tool_calls: list[ToolCall], notes: list[str] | None = None) -> ToolPlan:
    return ToolPlan(
        intent=intent,
        course_ids=[],
        target_direction=None,
        completed_courses=[],
        tool_calls=tool_calls,
        notes=notes or [],
    )


def test_dispatches_get_course_profile() -> None:
    fake_profile = CourseProfile(
        course_id="ECE 391",
        title="Systems Programming",
        description=None,
        credit_hours=None,
        prerequisites=None,
        career_tags=[],
        source_url=None,
    )
    collector = ToolTraceCollector()
    plan = _plan(
        "course_qa",
        [ToolCall(tool_name="get_course_profile", arguments={"course_id": "ECE 391"})],
    )

    with patch(
        "app.services.tools.dispatcher.get_course_profile", return_value=fake_profile
    ) as mocked:
        results = execute_plan(DummySession(), plan, collector)

    mocked.assert_called_once()
    assert results.course_profiles["ECE 391"] is fake_profile
    trace = collector.to_debug_trace()
    assert trace.intent == "course_qa"
    assert trace.tool_calls[0]["tool_name"] == "get_course_profile"
    assert trace.tool_calls[0]["status"] == "success"
    assert trace.tool_calls[0]["result_summary"] == {
        "found": True,
        "title": "Systems Programming",
    }


def test_dispatches_full_comparison_sequence_in_order() -> None:
    fake_profile = CourseProfile(
        course_id="ECE 408",
        title="Applied Parallel Programming",
        description=None,
        credit_hours=None,
        prerequisites=None,
        career_tags=["ai_infra"],
        source_url=None,
    )
    fake_gpa = GPAStats(course_id="ECE 408", average_gpa=3.5, instructor_stats=[])
    fake_comparison = CourseComparison(
        course_ids=["ECE 408", "CS 433"],
        dimension="ai_infra",
        courses=[
            CourseComparisonItem(
                course_id="ECE 408",
                title="Applied Parallel Programming",
                career_tags=["ai_infra"],
                direction_match="match",
                average_gpa=3.5,
                prerequisite_readiness="likely_ready",
                missing_prerequisites=[],
                notes=[],
            )
        ],
        notes=[],
    )
    plan = _plan(
        "comparison",
        [
            ToolCall("get_course_profile", {"course_id": "ECE 408"}),
            ToolCall("get_course_profile", {"course_id": "CS 433"}),
            ToolCall("get_gpa_stats", {"course_id": "ECE 408"}),
            ToolCall("get_gpa_stats", {"course_id": "CS 433"}),
            ToolCall(
                "compare_courses",
                {
                    "course_ids": ["ECE 408", "CS 433"],
                    "dimension": "ai_infra",
                    "completed_courses": [],
                },
            ),
        ],
    )
    collector = ToolTraceCollector()

    with patch(
        "app.services.tools.dispatcher.get_course_profile", return_value=fake_profile
    ), patch(
        "app.services.tools.dispatcher.get_gpa_stats", return_value=fake_gpa
    ), patch(
        "app.services.tools.dispatcher.compare_courses", return_value=fake_comparison
    ):
        results = execute_plan(DummySession(), plan, collector)

    assert results.comparison is fake_comparison
    assert collector.tool_names() == [
        "get_course_profile",
        "get_course_profile",
        "get_gpa_stats",
        "get_gpa_stats",
        "compare_courses",
    ]


def test_dispatches_recommendation_records_scores() -> None:
    fake_recs = CourseRecommendations(
        target_direction="ai_infra",
        completed_courses=[],
        recommendations=[
            CourseRecommendation(
                course_id="ECE 408",
                title="Applied Parallel Programming",
                score=0.86,
                score_breakdown={"direction_match": 1.0},
                reason_codes=["ai_infra_match"],
                notes=[],
            )
        ],
        notes=[],
    )
    plan = _plan(
        "recommendation",
        [
            ToolCall(
                "recommend_courses",
                {
                    "target_direction": "ai_infra",
                    "completed_courses": [],
                    "max_results": 5,
                },
            )
        ],
    )
    collector = ToolTraceCollector()

    with patch(
        "app.services.tools.dispatcher.recommend_courses", return_value=fake_recs
    ):
        results = execute_plan(DummySession(), plan, collector)

    assert results.recommendations is fake_recs
    trace = collector.to_debug_trace()
    assert trace.recommendation_scores[0]["course_id"] == "ECE 408"
    assert trace.recommendation_scores[0]["score"] == 0.86


def test_dispatches_search_records_chunks() -> None:
    fake_result = SearchCourseDocsResult(
        query="ECE 391",
        course_ids=["ECE 391"],
        docs=[
            RetrievedDoc(
                course_id="ECE 391",
                source_name="Mock Course Dataset",
                source_url="https://example.com/courses/ece-391",
                section_type="course_description",
                snippet="ECE 391 is a systems programming course.",
                score=0.42,
            )
        ],
        notes=["Fell back to sample chunks."],
    )
    plan = _plan(
        "course_qa",
        [
            ToolCall(
                "search_course_docs",
                {"query": "What is ECE 391?", "course_ids": ["ECE 391"], "top_k": 3},
            )
        ],
    )
    collector = ToolTraceCollector()

    with patch(
        "app.services.tools.dispatcher.run_search_course_docs",
        return_value=fake_result,
    ):
        results = execute_plan(DummySession(), plan, collector)

    assert results.search_result is fake_result
    trace = collector.to_debug_trace()
    assert trace.retrieved_chunks[0]["course_id"] == "ECE 391"
    # notes from search_result are surfaced into collector notes
    assert "Fell back to sample chunks." in collector.notes()


def test_tool_error_is_isolated_and_pipeline_continues() -> None:
    fake_profile = CourseProfile(
        course_id="ECE 391",
        title="Systems Programming",
        description=None,
        credit_hours=None,
        prerequisites=None,
        career_tags=[],
        source_url=None,
    )
    plan = _plan(
        "course_qa",
        [
            ToolCall("get_course_profile", {"course_id": "ECE 391"}),
            ToolCall("get_gpa_stats", {"course_id": "ECE 391"}),
        ],
    )
    collector = ToolTraceCollector()

    with patch(
        "app.services.tools.dispatcher.get_course_profile", return_value=fake_profile
    ), patch(
        "app.services.tools.dispatcher.get_gpa_stats",
        side_effect=RuntimeError("db down"),
    ):
        results = execute_plan(DummySession(), plan, collector)

    # First tool succeeded, second recorded as error, dispatcher did not abort.
    assert results.course_profiles["ECE 391"] is fake_profile
    trace = collector.to_debug_trace()
    assert [call["status"] for call in trace.tool_calls] == ["success", "error"]
    assert trace.tool_calls[1]["error"] == "db down"


def test_recommendation_without_direction_is_skipped_not_error() -> None:
    plan = _plan(
        "recommendation",
        [
            ToolCall(
                "recommend_courses",
                {"target_direction": None, "completed_courses": [], "max_results": 5},
            )
        ],
    )
    collector = ToolTraceCollector()

    with patch("app.services.tools.dispatcher.recommend_courses") as mocked:
        results = execute_plan(DummySession(), plan, collector)

    mocked.assert_not_called()
    assert results.recommendations is None
    trace = collector.to_debug_trace()
    assert trace.tool_calls[0]["status"] == "skipped"


def test_unknown_tool_name_is_skipped() -> None:
    plan = _plan("course_qa", [ToolCall("mystery_tool", {"x": 1})])
    collector = ToolTraceCollector()

    execute_plan(DummySession(), plan, collector)

    trace = collector.to_debug_trace()
    assert trace.tool_calls[0]["status"] == "skipped"
    assert "Unknown tool" in trace.tool_calls[0]["result_summary"]["reason"]


def test_plan_notes_are_carried_to_collector() -> None:
    plan = _plan(
        "recommendation",
        [],
        notes=["No target direction detected; ask the user."],
    )
    collector = ToolTraceCollector()

    execute_plan(DummySession(), plan, collector)

    assert "No target direction detected; ask the user." in collector.notes()
