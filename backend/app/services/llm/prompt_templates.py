"""Per-intent prompt templates used by ``answer_synthesis``.

Each intent has a dedicated system prompt (behavior contract) and a user
prompt builder that serializes ``DispatchedResults`` into an evidence block.
The templates keep the LLM grounded to the tool output — the system prompt
tells the model to refuse-if-no-evidence, the user prompt supplies the
evidence.

Prompt tuning happens here; ``answer_synthesis`` never assembles messages
itself. This keeps prompt engineering separable from pipeline plumbing.
"""

from app.services.llm.schemas import LLMMessage
from app.services.tools.dispatcher import DispatchedResults


SYSTEM_PROMPTS: dict[str, str] = {
    "course_qa": (
        "You are IlliniGuide, a UIUC ECE/CS academic advisor. "
        "Answer the user's question about the course using ONLY the retrieved evidence provided. "
        "If the evidence is insufficient, say so — do not invent details. "
        "Cite course ids and source names from the evidence. Keep answers under 5 sentences."
    ),
    "comparison": (
        "You are IlliniGuide, a UIUC ECE/CS academic advisor. "
        "Compare the courses using ONLY the structured comparison data and retrieved evidence provided. "
        "Highlight direction match, GPA data, prerequisite readiness, and any missing signals. "
        "Do not claim one course is objectively easier without supporting evidence. "
        "Keep the comparison under 6 sentences."
    ),
    "recommendation": (
        "You are IlliniGuide, a UIUC ECE/CS academic advisor. "
        "Recommend courses for the user's target direction using the ranked candidates provided. "
        "Explain briefly why each course is chosen (direction match, prerequisite readiness, GPA). "
        "Do NOT show internal numeric scores in the final answer — describe reasons in natural language. "
        "Keep the answer under 6 sentences."
    ),
    "prereq_check": (
        "You are IlliniGuide, a UIUC ECE/CS academic advisor. "
        "Report whether the student is likely ready for the target course based on the prerequisite check. "
        "If there are missing prerequisites, list them plainly. "
        "Note that this is a course-id-level check, not an official degree audit. "
        "Keep the answer under 4 sentences."
    ),
}

DEFAULT_SYSTEM_PROMPT = (
    "You are IlliniGuide, a UIUC ECE/CS academic advisor. "
    "Answer the user's question using the retrieved evidence provided. "
    "If evidence is insufficient, say so plainly and do not invent details."
)


def build_prompt_messages(
    intent: str,
    query: str,
    results: DispatchedResults,
) -> list[LLMMessage]:
    system_prompt = SYSTEM_PROMPTS.get(intent, DEFAULT_SYSTEM_PROMPT)
    user_prompt = _build_user_prompt(intent, query, results)
    return [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_prompt),
    ]


def _build_user_prompt(
    intent: str, query: str, results: DispatchedResults
) -> str:
    if intent == "course_qa":
        return _user_prompt_course_qa(query, results)
    if intent == "comparison":
        return _user_prompt_comparison(query, results)
    if intent == "recommendation":
        return _user_prompt_recommendation(query, results)
    if intent == "prereq_check":
        return _user_prompt_prereq(query, results)
    return _user_prompt_default(query, results)


def _user_prompt_course_qa(query: str, results: DispatchedResults) -> str:
    parts = [f"User question: {query}", ""]

    profiles = [p for p in results.course_profiles.values() if p is not None]
    if profiles:
        parts.append("Course profiles from the database:")
        for profile in profiles:
            tag_suffix = f" (tags: {profile.career_tags})" if profile.career_tags else ""
            parts.append(f"- {profile.course_id} — {profile.title}{tag_suffix}")
            if profile.prerequisites:
                parts.append(f"  Prerequisites: {profile.prerequisites}")
        parts.append("")

    docs = results.search_result.docs if results.search_result else []
    if docs:
        parts.append("Retrieved evidence:")
        for doc in docs[:5]:
            parts.append(f"- [{doc.course_id} · {doc.source_name}] {doc.snippet}")
        parts.append("")

    if not profiles and not docs:
        parts.append("(No evidence retrieved from database or sample chunks.)")

    return "\n".join(parts).strip()


def _user_prompt_comparison(query: str, results: DispatchedResults) -> str:
    parts = [f"User question: {query}", ""]

    if results.comparison and results.comparison.courses:
        parts.append("Structured comparison:")
        for item in results.comparison.courses:
            parts.append(
                f"- {item.course_id} — {item.title}\n"
                f"  direction_match={item.direction_match}, "
                f"average_gpa={item.average_gpa}, "
                f"prerequisite_readiness={item.prerequisite_readiness}"
            )
            if item.missing_prerequisites:
                parts.append(
                    f"  missing_prerequisites: {item.missing_prerequisites}"
                )
            if item.notes:
                parts.append(f"  notes: {item.notes}")
        parts.append("")
    else:
        parts.append(
            "(No structured comparison available — one or more courses not found.)"
        )
        parts.append("")

    docs = results.search_result.docs if results.search_result else []
    if docs:
        parts.append("Retrieved evidence:")
        for doc in docs[:5]:
            parts.append(f"- [{doc.course_id} · {doc.source_name}] {doc.snippet}")

    return "\n".join(parts).strip()


def _user_prompt_recommendation(query: str, results: DispatchedResults) -> str:
    parts = [f"User question: {query}", ""]

    recs = results.recommendations
    if recs is None:
        parts.append(
            "(No target direction was detected. Ask the user which direction they want, "
            "e.g. AI infra, systems, ML, security.)"
        )
        return "\n".join(parts).strip()

    parts.append(f"Target direction: {recs.target_direction}")
    if recs.completed_courses:
        parts.append(f"Completed courses: {recs.completed_courses}")

    if recs.recommendations:
        parts.append("")
        parts.append(
            "Ranked candidates (higher score = better match; do NOT show numbers to the user):"
        )
        for rec in recs.recommendations:
            parts.append(
                f"- {rec.course_id} — {rec.title}\n"
                f"  reasons: {rec.reason_codes}\n"
                f"  score: {rec.score} breakdown={rec.score_breakdown}"
            )
            if rec.notes:
                parts.append(f"  notes: {rec.notes}")
    else:
        parts.append("")
        parts.append(
            "(No matching courses found for this direction in the current dataset.)"
        )

    return "\n".join(parts).strip()


def _user_prompt_prereq(query: str, results: DispatchedResults) -> str:
    parts = [f"User question: {query}", ""]

    if not results.prereq_checks:
        parts.append(
            "(No prerequisite check was performed — no target course was resolved.)"
        )
        return "\n".join(parts).strip()

    parts.append("Prerequisite check results:")
    for target, check in results.prereq_checks.items():
        if check is None:
            parts.append(f"- {target}: course not found in database.")
            continue
        parts.append(f"- {target}: readiness = {check.readiness}")
        if check.missing_prerequisites:
            parts.append(f"  missing: {check.missing_prerequisites}")
        if check.notes:
            parts.append(f"  notes: {check.notes}")

    return "\n".join(parts).strip()


def _user_prompt_default(query: str, results: DispatchedResults) -> str:
    return f"User question: {query}\n\n(No structured tool results available.)"
