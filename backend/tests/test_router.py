import pytest

from app.services.tools.router import plan_tools


def _tool_names(plan) -> list[str]:
    return [call.tool_name for call in plan.tool_calls]


def test_course_qa_single_course() -> None:
    plan = plan_tools("What is ECE 391 about?")

    assert plan.intent == "course_qa"
    assert plan.course_ids == ["ECE 391"]
    assert plan.target_direction is None
    assert _tool_names(plan) == ["get_course_profile", "search_course_docs"]
    assert plan.tool_calls[0].arguments == {"course_id": "ECE 391"}
    assert plan.tool_calls[1].arguments["course_ids"] == ["ECE 391"]


def test_comparison_two_courses_with_verb() -> None:
    plan = plan_tools("Compare ECE 408 and CS 433 for AI infra")

    assert plan.intent == "comparison"
    assert plan.course_ids == ["ECE 408", "CS 433"]
    assert plan.target_direction == "ai_infra"
    assert _tool_names(plan) == [
        "get_course_profile",
        "get_course_profile",
        "get_gpa_stats",
        "get_gpa_stats",
        "compare_courses",
    ]
    compare_call = plan.tool_calls[-1]
    assert compare_call.arguments == {
        "course_ids": ["ECE 408", "CS 433"],
        "dimension": "ai_infra",
        "completed_courses": [],
    }


def test_comparison_no_verb_multiple_ids_still_routes_to_comparison() -> None:
    plan = plan_tools("ECE 408 CS 433")

    assert plan.intent == "comparison"
    assert plan.course_ids == ["ECE 408", "CS 433"]


def test_comparison_one_id_downgrades_to_course_qa() -> None:
    plan = plan_tools("Compare ECE 408 to what?")

    assert plan.intent == "course_qa"
    assert plan.course_ids == ["ECE 408"]
    assert any("Comparison needs at least two" in note for note in plan.notes)


def test_recommendation_with_direction() -> None:
    plan = plan_tools("What courses are good for AI infra?")

    assert plan.intent == "recommendation"
    assert plan.target_direction == "ai_infra"
    assert _tool_names(plan) == ["recommend_courses"]
    assert plan.tool_calls[0].arguments == {
        "target_direction": "ai_infra",
        "completed_courses": [],
        "max_results": 5,
    }
    assert plan.notes == []


def test_recommendation_without_direction_adds_note() -> None:
    plan = plan_tools("Recommend a course for me")

    assert plan.intent == "recommendation"
    assert plan.target_direction is None
    assert any("target direction" in note.lower() for note in plan.notes)


def test_prereq_check_with_course() -> None:
    plan = plan_tools("Am I ready for ECE 408?", completed_courses=["ECE 220"])

    assert plan.intent == "prereq_check"
    assert plan.course_ids == ["ECE 408"]
    assert plan.completed_courses == ["ECE 220"]
    assert _tool_names(plan) == ["check_prerequisites"]
    assert plan.tool_calls[0].arguments == {
        "target_course": "ECE 408",
        "completed_courses": ["ECE 220"],
    }


@pytest.mark.parametrize(
    "query",
    [
        "Which classes must I complete before ECE 391?",
        "What do I need before taking ECE 411?",
        "What prior coursework is required for ECE 470?",
    ],
)
def test_prerequisite_phrasings_route_to_structured_tool(query: str) -> None:
    plan = plan_tools(query)

    assert plan.intent == "prereq_check"
    assert _tool_names(plan) == ["check_prerequisites"]


def test_prereq_check_without_course_downgrades() -> None:
    plan = plan_tools("Am I ready for that class?")

    assert plan.intent == "course_qa"
    assert any("Prerequisite check" in note for note in plan.notes)


def test_prereq_beats_comparison_by_priority() -> None:
    plan = plan_tools("Am I ready for ECE 408 or should I compare it with CS 433?")

    assert plan.intent == "prereq_check"
    assert plan.course_ids == ["ECE 408"]


def test_completed_courses_plumbed_into_comparison() -> None:
    plan = plan_tools(
        "Compare ECE 408 and CS 433",
        completed_courses=["ECE 220", "ECE 391"],
    )

    assert plan.completed_courses == ["ECE 220", "ECE 391"]
    compare_call = plan.tool_calls[-1]
    assert compare_call.arguments["completed_courses"] == ["ECE 220", "ECE 391"]


def test_fallback_gibberish_returns_search_only() -> None:
    plan = plan_tools("xyzzy nothing here")

    assert plan.intent == "course_qa"
    assert plan.course_ids == []
    assert _tool_names(plan) == ["search_course_docs"]
    assert plan.tool_calls[0].arguments == {"query": "xyzzy nothing here", "top_k": 5}


def test_empty_query_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        plan_tools("   ")
