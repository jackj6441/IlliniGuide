from app.services.llm.prompt_templates import (
    DEFAULT_SYSTEM_PROMPT,
    SYSTEM_PROMPTS,
    build_prompt_messages,
)
from app.services.tools.dispatcher import DispatchedResults
from app.services.tools.schemas import (
    CourseComparison,
    CourseComparisonItem,
    CourseProfile,
    CourseRecommendation,
    CourseRecommendations,
    PrerequisiteCheck,
    RetrievedDoc,
    SearchCourseDocsResult,
)


def _profile(course_id: str, **overrides) -> CourseProfile:
    defaults = dict(
        course_id=course_id,
        title="Course Title",
        description=None,
        credit_hours=None,
        prerequisites=None,
        career_tags=[],
        source_url=None,
    )
    defaults.update(overrides)
    return CourseProfile(**defaults)


def _search_result(docs: list[RetrievedDoc]) -> SearchCourseDocsResult:
    return SearchCourseDocsResult(
        query="",
        course_ids=[],
        docs=docs,
        notes=[],
    )


def _doc(course_id: str, snippet: str) -> RetrievedDoc:
    return RetrievedDoc(
        course_id=course_id,
        source_name="Course Database",
        source_url="https://example.com",
        section_type="course_profile",
        snippet=snippet,
        score=0.5,
    )


def test_build_prompt_messages_returns_system_and_user() -> None:
    messages = build_prompt_messages(
        "course_qa", "What is ECE 391?", DispatchedResults()
    )

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == SYSTEM_PROMPTS["course_qa"]
    assert messages[1].role == "user"
    assert "What is ECE 391?" in messages[1].content


def test_course_qa_prompt_includes_profile_and_evidence() -> None:
    profile = _profile(
        "ECE 391", title="Systems Programming", prerequisites="ECE 220"
    )
    results = DispatchedResults(
        course_profiles={"ECE 391": profile},
        search_result=_search_result(
            [_doc("ECE 391", "systems programming and low-level C")]
        ),
    )

    messages = build_prompt_messages("course_qa", "What is ECE 391?", results)
    user_prompt = messages[1].content

    assert "ECE 391 — Systems Programming" in user_prompt
    assert "Prerequisites: ECE 220" in user_prompt
    assert "systems programming and low-level C" in user_prompt
    assert "Course Database" in user_prompt


def test_course_qa_prompt_handles_missing_evidence() -> None:
    results = DispatchedResults()

    messages = build_prompt_messages("course_qa", "What is XYZ 999?", results)
    user_prompt = messages[1].content

    assert "No evidence retrieved" in user_prompt


def test_comparison_prompt_includes_structured_signals() -> None:
    comparison = CourseComparison(
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
            ),
            CourseComparisonItem(
                course_id="CS 433",
                title="Computer System Organization",
                career_tags=["computer_architecture"],
                direction_match="no_match",
                average_gpa=3.2,
                prerequisite_readiness="missing_prerequisites",
                missing_prerequisites=["CS 233"],
                notes=[],
            ),
        ],
        notes=[],
    )
    results = DispatchedResults(comparison=comparison)

    messages = build_prompt_messages(
        "comparison", "Compare ECE 408 and CS 433 for AI infra", results
    )
    user_prompt = messages[1].content

    assert "direction_match=match" in user_prompt
    assert "direction_match=no_match" in user_prompt
    assert "average_gpa=3.5" in user_prompt
    assert "missing_prerequisites: ['CS 233']" in user_prompt


def test_comparison_prompt_handles_empty_comparison() -> None:
    results = DispatchedResults()

    messages = build_prompt_messages(
        "comparison", "Compare X and Y", results
    )
    assert "No structured comparison available" in messages[1].content


def test_recommendation_prompt_includes_reason_codes_and_scores() -> None:
    recs = CourseRecommendations(
        target_direction="ai_infra",
        completed_courses=["ECE 220"],
        recommendations=[
            CourseRecommendation(
                course_id="ECE 408",
                title="Applied Parallel Programming",
                score=0.86,
                score_breakdown={"direction_match": 1.0},
                reason_codes=["ai_infra_match", "prerequisites_satisfied"],
                notes=[],
            )
        ],
        notes=[],
    )
    results = DispatchedResults(recommendations=recs)

    messages = build_prompt_messages(
        "recommendation", "What is good for AI infra?", results
    )
    user_prompt = messages[1].content

    assert "Target direction: ai_infra" in user_prompt
    assert "Completed courses: ['ECE 220']" in user_prompt
    assert "ai_infra_match" in user_prompt
    assert "score: 0.86" in user_prompt
    # System prompt reminds LLM to not show numbers
    assert "do NOT show" in messages[0].content.lower() or "do not show" in messages[0].content.lower()


def test_recommendation_prompt_when_no_direction_detected() -> None:
    results = DispatchedResults()

    messages = build_prompt_messages(
        "recommendation", "Recommend something", results
    )

    assert "No target direction was detected" in messages[1].content


def test_prereq_prompt_lists_missing_prereqs() -> None:
    check = PrerequisiteCheck(
        target_course="ECE 408",
        completed_courses=["ECE 220"],
        missing_prerequisites=["ECE 391"],
        readiness="missing_prerequisites",
        notes=["This is a course-id check, not an official degree audit."],
    )
    results = DispatchedResults(prereq_checks={"ECE 408": check})

    messages = build_prompt_messages(
        "prereq_check", "Am I ready for ECE 408?", results
    )
    user_prompt = messages[1].content

    assert "readiness = missing_prerequisites" in user_prompt
    assert "missing: ['ECE 391']" in user_prompt


def test_prereq_prompt_when_no_check_present() -> None:
    results = DispatchedResults()

    messages = build_prompt_messages("prereq_check", "Am I ready?", results)

    assert "No prerequisite check was performed" in messages[1].content


def test_unknown_intent_uses_default_system_prompt() -> None:
    results = DispatchedResults()

    messages = build_prompt_messages("gibberish_intent", "hi", results)

    assert messages[0].content == DEFAULT_SYSTEM_PROMPT
    assert "No structured tool results available" in messages[1].content
