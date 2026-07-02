from app.services.llm.client import LLMClient
from app.services.llm.prompt_templates import build_prompt_messages
from app.services.tools.dispatcher import DispatchedResults
from app.services.tools.trace import ToolTraceCollector


LLM_TODO_SUFFIX = (
    "TODO: this is the template fallback, used only when the LLM call fails."
)


async def build_answer(
    intent: str,
    query: str,
    results: DispatchedResults,
    llm_client: LLMClient,
    collector: ToolTraceCollector,
) -> str:
    """Return a grounded natural-language answer for the given intent.

    Primary path: build intent-specific prompt messages, call the LLM,
    return its content. Fallback path: on any LLM error, record a note
    and return a deterministic template answer so the user is not blocked
    on infrastructure hiccups. The LLM call is timed via the collector,
    so its latency and status show up in the debug trace just like any
    other tool.
    """
    messages = build_prompt_messages(intent, query, results)

    try:
        with collector.time_tool(
            "llm_generate",
            {
                "backend": llm_client.backend_name,
                "model": llm_client.model_name,
                "n_messages": len(messages),
            },
        ) as span:
            response = await llm_client.generate(messages)
            span.set_result_summary(
                {
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "backend_latency_ms": response.latency_ms,
                }
            )
        return response.content
    except Exception as exc:
        collector.add_note(
            f"LLM call failed ({type(exc).__name__}: {exc}); "
            "falling back to deterministic template answer."
        )
        return _template_fallback(intent, results)


def _template_fallback(intent: str, results: DispatchedResults) -> str:
    if intent == "course_qa":
        return _template_course_qa(results)
    if intent == "comparison":
        return _template_comparison(results)
    if intent == "recommendation":
        return _template_recommendation(results)
    if intent == "prereq_check":
        return _template_prereq(results)
    return "Unable to synthesize an answer for this query. " + LLM_TODO_SUFFIX


def _template_course_qa(results: DispatchedResults) -> str:
    docs = results.search_result.docs if results.search_result else []
    if not docs:
        return (
            "I could not find enough evidence in the course dataset to answer this. "
            + LLM_TODO_SUFFIX
        )
    course_ids = ", ".join(_unique_preserve_order(doc.course_id for doc in docs[:3]))
    snippets = " ".join(doc.snippet for doc in docs[:2])
    return f"Based on retrieved evidence for {course_ids}: {snippets} {LLM_TODO_SUFFIX}"


def _template_comparison(results: DispatchedResults) -> str:
    if results.comparison is None or not results.comparison.courses:
        return (
            "Comparison unavailable — one or more courses could not be found. "
            + LLM_TODO_SUFFIX
        )
    parts = []
    for item in results.comparison.courses:
        parts.append(
            f"{item.course_id} ({item.title}): "
            f"direction={item.direction_match}, "
            f"average_gpa={item.average_gpa}, "
            f"readiness={item.prerequisite_readiness}"
        )
    return "Structured comparison — " + "; ".join(parts) + ". " + LLM_TODO_SUFFIX


def _template_recommendation(results: DispatchedResults) -> str:
    recs = results.recommendations
    if recs is None:
        return (
            "I need a target direction to recommend courses. Try 'AI infra', 'systems', "
            "or 'ML' and I can give ranked suggestions. " + LLM_TODO_SUFFIX
        )
    if not recs.recommendations:
        return (
            f"No matching courses found for direction '{recs.target_direction}' in the "
            "current dataset. " + LLM_TODO_SUFFIX
        )
    parts = [f"{r.course_id} ({r.title})" for r in recs.recommendations[:5]]
    return (
        f"Top recommendations for {recs.target_direction}: "
        + ", ".join(parts)
        + ". "
        + LLM_TODO_SUFFIX
    )


def _template_prereq(results: DispatchedResults) -> str:
    if not results.prereq_checks:
        return (
            "Prerequisite check unavailable — no target course was resolved. "
            + LLM_TODO_SUFFIX
        )
    parts = []
    for target, check in results.prereq_checks.items():
        if check is None:
            parts.append(f"{target}: not found in database")
            continue
        detail = f"readiness={check.readiness}"
        if check.missing_prerequisites:
            detail += f", missing={check.missing_prerequisites}"
        parts.append(f"{target}: {detail}")
    return "Prerequisite check — " + "; ".join(parts) + ". " + LLM_TODO_SUFFIX


def _unique_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
