import re
from typing import Any

from app.services.rag.normalize import extract_course_ids
from app.services.tools.schemas import ToolCall, ToolPlan


PREREQ_PATTERN = re.compile(
    r"\b(prereq|prerequisite|prerequisites|ready for|can i take|am i ready)\b",
    re.IGNORECASE,
)
RECOMMEND_PATTERN = re.compile(
    r"\b(recommend|recommendation|what should i take|good for|useful for|courses for)\b",
    re.IGNORECASE,
)
COMPARE_PATTERN = re.compile(
    r"\b(compare|vs|versus|difference between)\b",
    re.IGNORECASE,
)

# Order matters: longer / more specific phrases must appear before shorter ones
# that could match as a substring.
DIRECTION_PHRASES: tuple[tuple[str, str], ...] = (
    ("ai infrastructure", "ai_infra"),
    ("ai infra", "ai_infra"),
    ("ml systems", "ai_infra"),
    ("machine learning", "ai_ml"),
    ("computer architecture", "computer_architecture"),
    ("computer vision", "robotics_cv"),
    ("data science", "data_science"),
    ("software engineering", "software_engineering"),
    ("robotics", "robotics_cv"),
    ("security", "security"),
    ("systems", "systems"),
    ("ai", "ai_ml"),
    ("ml", "ai_ml"),
)


DEFAULT_RECOMMEND_MAX_RESULTS = 5


def plan_tools(query: str, completed_courses: list[str] | None = None) -> ToolPlan:
    stripped = query.strip()
    if not stripped:
        raise ValueError("query must be a non-empty string")

    course_ids = extract_course_ids(stripped)
    completed = list(completed_courses or [])

    if PREREQ_PATTERN.search(stripped):
        return _plan_prereq_check(stripped, course_ids, completed)

    if RECOMMEND_PATTERN.search(stripped):
        return _plan_recommendation(stripped, course_ids, completed)

    if COMPARE_PATTERN.search(stripped) or len(course_ids) >= 2:
        return _plan_comparison(stripped, course_ids, completed)

    return _plan_course_qa(stripped, course_ids, completed)


def _plan_prereq_check(
    query: str, course_ids: list[str], completed: list[str]
) -> ToolPlan:
    if not course_ids:
        return _plan_course_qa(
            query,
            course_ids,
            completed,
            extra_notes=[
                "Prerequisite check requires a target course id in the query.",
            ],
        )

    target_course = course_ids[0]
    tool_calls = [
        ToolCall(
            tool_name="check_prerequisites",
            arguments={"target_course": target_course, "completed_courses": completed},
        ),
    ]
    return ToolPlan(
        intent="prereq_check",
        course_ids=[target_course],
        target_direction=None,
        completed_courses=completed,
        tool_calls=tool_calls,
        notes=[],
    )


def _plan_recommendation(
    query: str, course_ids: list[str], completed: list[str]
) -> ToolPlan:
    direction = _extract_direction(query)
    notes: list[str] = []
    if direction is None:
        notes.append(
            "No target direction detected; ask the user which direction they want."
        )

    tool_calls = [
        ToolCall(
            tool_name="recommend_courses",
            arguments={
                "target_direction": direction,
                "completed_courses": completed,
                "max_results": DEFAULT_RECOMMEND_MAX_RESULTS,
            },
        ),
    ]
    return ToolPlan(
        intent="recommendation",
        course_ids=course_ids,
        target_direction=direction,
        completed_courses=completed,
        tool_calls=tool_calls,
        notes=notes,
    )


def _plan_comparison(
    query: str, course_ids: list[str], completed: list[str]
) -> ToolPlan:
    if len(course_ids) < 2:
        return _plan_course_qa(
            query,
            course_ids,
            completed,
            extra_notes=[
                "Comparison needs at least two course ids; falling back to a single-course lookup.",
            ],
        )

    direction = _extract_direction(query)
    tool_calls: list[ToolCall] = []
    for course_id in course_ids:
        tool_calls.append(
            ToolCall(tool_name="get_course_profile", arguments={"course_id": course_id})
        )
    for course_id in course_ids:
        tool_calls.append(
            ToolCall(tool_name="get_gpa_stats", arguments={"course_id": course_id})
        )
    tool_calls.append(
        ToolCall(
            tool_name="compare_courses",
            arguments={
                "course_ids": course_ids,
                "dimension": direction,
                "completed_courses": completed,
            },
        )
    )
    return ToolPlan(
        intent="comparison",
        course_ids=course_ids,
        target_direction=direction,
        completed_courses=completed,
        tool_calls=tool_calls,
        notes=[],
    )


def _plan_course_qa(
    query: str,
    course_ids: list[str],
    completed: list[str],
    extra_notes: list[str] | None = None,
) -> ToolPlan:
    tool_calls: list[ToolCall] = []
    if course_ids:
        for course_id in course_ids:
            tool_calls.append(
                ToolCall(
                    tool_name="get_course_profile", arguments={"course_id": course_id}
                )
            )
    tool_calls.append(
        ToolCall(
            tool_name="search_course_docs",
            arguments=_search_arguments(query, course_ids),
        )
    )
    return ToolPlan(
        intent="course_qa",
        course_ids=course_ids,
        target_direction=None,
        completed_courses=completed,
        tool_calls=tool_calls,
        notes=list(extra_notes or []),
    )


def _search_arguments(query: str, course_ids: list[str]) -> dict[str, Any]:
    args: dict[str, Any] = {"query": query, "top_k": 5}
    if course_ids:
        args["course_ids"] = course_ids
    return args


def _extract_direction(query: str) -> str | None:
    lowered = query.lower()
    for phrase, tag in DIRECTION_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return tag
    return None
