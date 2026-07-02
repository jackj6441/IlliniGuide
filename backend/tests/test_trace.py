import pytest

from app.services.tools.trace import ToolTraceCollector


def test_time_tool_records_success() -> None:
    collector = ToolTraceCollector()
    collector.set_intent("course_qa")

    with collector.time_tool("get_course_profile", {"course_id": "ECE 391"}) as span:
        span.set_result_summary({"found": True, "title": "Systems Programming"})

    trace = collector.to_debug_trace()
    assert trace.intent == "course_qa"
    assert len(trace.tool_calls) == 1
    call = trace.tool_calls[0]
    assert call["tool_name"] == "get_course_profile"
    assert call["arguments"] == {"course_id": "ECE 391"}
    assert call["status"] == "success"
    assert call["error"] is None
    assert call["latency_ms"] >= 0
    assert call["result_summary"] == {"found": True, "title": "Systems Programming"}


def test_time_tool_records_error_and_reraises() -> None:
    collector = ToolTraceCollector()

    with pytest.raises(RuntimeError, match="boom"):
        with collector.time_tool("broken_tool", {"x": 1}):
            raise RuntimeError("boom")

    trace = collector.to_debug_trace()
    call = trace.tool_calls[0]
    assert call["status"] == "error"
    assert call["error"] == "boom"
    assert call["latency_ms"] >= 0


def test_record_skipped_tool_has_zero_latency() -> None:
    collector = ToolTraceCollector()
    collector.record_skipped_tool(
        "compare_courses",
        {"course_ids": ["ECE 408"]},
        reason="Only one course id — comparison not applicable.",
    )

    trace = collector.to_debug_trace()
    call = trace.tool_calls[0]
    assert call["status"] == "skipped"
    assert call["latency_ms"] == 0
    assert call["result_summary"] == {
        "reason": "Only one course id — comparison not applicable.",
    }


def test_tool_names_returns_call_order() -> None:
    collector = ToolTraceCollector()
    with collector.time_tool("get_course_profile", {}):
        pass
    with collector.time_tool("search_course_docs", {}):
        pass
    collector.record_skipped_tool("compare_courses", {}, "n/a")

    assert collector.tool_names() == [
        "get_course_profile",
        "search_course_docs",
        "compare_courses",
    ]


def test_to_debug_trace_carries_chunks_and_scores() -> None:
    collector = ToolTraceCollector()
    collector.set_intent("recommendation")
    collector.record_chunks(
        [{"course_id": "ECE 408", "snippet": "GPU programming", "score": 0.9}]
    )
    collector.record_recommendation_scores(
        [
            {
                "course_id": "ECE 408",
                "score": 0.86,
                "breakdown": {"direction_match": 1.0},
            }
        ]
    )

    trace = collector.to_debug_trace()
    assert trace.retrieved_chunks[0]["course_id"] == "ECE 408"
    assert trace.recommendation_scores[0]["score"] == 0.86


def test_to_debug_trace_defaults_intent_to_unknown() -> None:
    collector = ToolTraceCollector()
    trace = collector.to_debug_trace()
    assert trace.intent == "unknown"
    assert trace.tool_calls == []


def test_notes_are_recorded_and_readable() -> None:
    collector = ToolTraceCollector()
    collector.add_note("No target direction detected.")
    collector.add_note("Fell back to sample chunks.")

    assert collector.notes() == [
        "No target direction detected.",
        "Fell back to sample chunks.",
    ]
