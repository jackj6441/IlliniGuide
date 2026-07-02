from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services.tools.compare_tools import compare_courses
from app.services.tools.course_tools import get_course_profile
from app.services.tools.gpa_tools import get_gpa_stats
from app.services.tools.prereq_tools import check_prerequisites
from app.services.tools.recommend_tools import recommend_courses
from app.services.tools.schemas import (
    CourseComparison,
    CourseProfile,
    CourseRecommendations,
    GPAStats,
    PrerequisiteCheck,
    SearchCourseDocsRequest,
    SearchCourseDocsResult,
    ToolCall,
    ToolPlan,
)
from app.services.tools.search_tools import search_course_docs as run_search_course_docs
from app.services.tools.trace import ToolTraceCollector


@dataclass
class DispatchedResults:
    course_profiles: dict[str, CourseProfile | None] = field(default_factory=dict)
    gpa_stats: dict[str, GPAStats | None] = field(default_factory=dict)
    prereq_checks: dict[str, PrerequisiteCheck | None] = field(default_factory=dict)
    comparison: CourseComparison | None = None
    recommendations: CourseRecommendations | None = None
    search_result: SearchCourseDocsResult | None = None


def execute_plan(
    session: Session,
    plan: ToolPlan,
    collector: ToolTraceCollector,
) -> DispatchedResults:
    collector.set_intent(plan.intent)
    for note in plan.notes:
        collector.add_note(note)

    results = DispatchedResults()
    for call in plan.tool_calls:
        try:
            _dispatch(session, call, collector, results)
        except Exception:
            # Error already captured by collector.time_tool; continue with next tool
            # so a single tool failure does not abort the whole request.
            continue
    return results


def _dispatch(
    session: Session,
    call: ToolCall,
    collector: ToolTraceCollector,
    results: DispatchedResults,
) -> None:
    name = call.tool_name
    args = call.arguments

    if name == "get_course_profile":
        with collector.time_tool(name, args) as span:
            profile = get_course_profile(session, args["course_id"])
            results.course_profiles[args["course_id"]] = profile
            span.set_result_summary(
                {
                    "found": profile is not None,
                    "title": profile.title if profile else None,
                }
            )
        return

    if name == "get_gpa_stats":
        with collector.time_tool(name, args) as span:
            stats = get_gpa_stats(session, args["course_id"])
            results.gpa_stats[args["course_id"]] = stats
            span.set_result_summary(
                {
                    "found": stats is not None,
                    "average_gpa": stats.average_gpa if stats else None,
                }
            )
        return

    if name == "check_prerequisites":
        with collector.time_tool(name, args) as span:
            check = check_prerequisites(
                session,
                args["target_course"],
                completed_courses=args.get("completed_courses"),
            )
            results.prereq_checks[args["target_course"]] = check
            span.set_result_summary(
                {
                    "readiness": check.readiness if check else "course_not_found",
                    "missing_count": (
                        len(check.missing_prerequisites) if check else 0
                    ),
                }
            )
        return

    if name == "compare_courses":
        with collector.time_tool(name, args) as span:
            comparison = compare_courses(
                session,
                args["course_ids"],
                dimension=args.get("dimension"),
                completed_courses=args.get("completed_courses"),
            )
            results.comparison = comparison
            span.set_result_summary({"n_courses": len(comparison.courses)})
        return

    if name == "recommend_courses":
        direction = args.get("target_direction")
        if not direction:
            collector.record_skipped_tool(
                name, args, "No target direction; recommendation cannot run."
            )
            return
        with collector.time_tool(name, args) as span:
            recs = recommend_courses(
                session,
                direction,
                completed_courses=args.get("completed_courses"),
                max_results=args.get("max_results", 5),
            )
            results.recommendations = recs
            collector.record_recommendation_scores(
                [
                    {
                        "course_id": rec.course_id,
                        "title": rec.title,
                        "score": rec.score,
                        "score_breakdown": rec.score_breakdown,
                        "reason_codes": rec.reason_codes,
                    }
                    for rec in recs.recommendations
                ]
            )
            span.set_result_summary({"n_recommendations": len(recs.recommendations)})
        return

    if name == "search_course_docs":
        request = SearchCourseDocsRequest(
            query=args["query"],
            course_ids=args.get("course_ids"),
            top_k=args.get("top_k", 5),
        )
        with collector.time_tool(name, args) as span:
            result = run_search_course_docs(session, request)
            results.search_result = result
            span.set_result_summary({"n_docs": len(result.docs)})
            collector.record_chunks(
                [
                    {
                        "course_id": doc.course_id,
                        "source_name": doc.source_name,
                        "section_type": doc.section_type,
                        "score": doc.score,
                        "snippet": doc.snippet,
                    }
                    for doc in result.docs
                ]
            )
            for note in result.notes:
                collector.add_note(note)
        return

    collector.record_skipped_tool(name, args, f"Unknown tool: {name}")
