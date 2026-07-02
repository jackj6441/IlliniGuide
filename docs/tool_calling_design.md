# Tool Calling Design

Status: Partial

The tool layer separates reliable structured computation from LLM explanation. Tools should query databases, run deterministic checks, or retrieve evidence. The LLM should not invent course facts directly.

## Implemented

### `get_course_profile`

Status: Implemented

Purpose:

Return structured course information from the `courses` table.

Input:

```json
{
  "course_id": "ECE 210"
}
```

Output:

```json
{
  "course_id": "ECE 210",
  "title": "Analog Signal Processing",
  "description": null,
  "credit_hours": null,
  "prerequisites": "Credit in ECE 110 ...",
  "career_tags": [],
  "source_url": "https://ece.illinois.edu/academics/courses"
}
```

### `get_gpa_stats`

Status: Implemented

Purpose:

Return structured GPA evidence from the `gpa_stats` table. This tool computes a course-level average from available rows and preserves instructor/term-level source evidence for later comparison and explanation.

Input:

```json
{
  "course_id": "CS 100",
  "instructor_name": null
}
```

Output:

```json
{
  "course_id": "CS 100",
  "average_gpa": 3.42,
  "instructor_stats": [
    {
      "instructor_name": "Example Instructor",
      "term": "Fall 2025",
      "average_gpa": 3.42,
      "grade_distribution": {},
      "source_url": "https://waf.cs.illinois.edu/visualizations/Grade-Disparities-and-Accolades-by-Instructor/"
    }
  ]
}
```

### `check_prerequisites`

Status: Implemented

Purpose:

Check whether the user's completed courses satisfy the parseable course-ID prerequisites for a target course. This is not a full official degree audit; non-course conditions such as senior standing are returned as notes or `unknown`.

Input:

```json
{
  "target_course": "ECE 391",
  "completed_courses": ["ECE 220"]
}
```

Output:

```json
{
  "target_course": "ECE 391",
  "completed_courses": ["ECE 220"],
  "missing_prerequisites": [],
  "readiness": "likely_ready",
  "notes": ["All parseable course prerequisite groups are satisfied."]
}
```

### `compare_courses`

Status: Implemented

Purpose:

Combine structured course profile, GPA, prerequisite readiness, and optional career-direction tags into a testable comparison object. This tool does not call the LLM and does not write the final advisor-style answer.

Input:

```json
{
  "course_ids": ["ECE 408", "CS 433"],
  "dimension": "ai_infra",
  "completed_courses": ["ECE 220"]
}
```

Output:

```json
{
  "course_ids": ["ECE 408", "CS 433"],
  "dimension": "ai_infra",
  "courses": [
    {
      "course_id": "ECE 408",
      "title": "Applied Parallel Programming",
      "career_tags": ["ai_infra"],
      "direction_match": "match",
      "average_gpa": 3.5,
      "prerequisite_readiness": "likely_ready",
      "missing_prerequisites": [],
      "notes": []
    }
  ],
  "notes": []
}
```

### `recommend_courses`

Status: Implemented

Purpose:

Recommend courses for a target direction using explicit scoring components. The numeric score is an internal/debug signal and should not be shown in the normal user UI by default.

Courses must have a matching `career_tags` entry to be recommended in this first version. This prevents GPA or prerequisite signals from producing unrelated recommendations.

Input:

```json
{
  "target_direction": "ai_infra",
  "completed_courses": ["ECE 220"],
  "max_results": 5
}
```

Output:

```json
{
  "target_direction": "ai_infra",
  "completed_courses": ["ECE 220"],
  "recommendations": [
    {
      "course_id": "ECE 408",
      "title": "Applied Parallel Programming",
      "score": 0.86,
      "score_breakdown": {
        "direction_match": 1.0,
        "prerequisite_readiness": 1.0,
        "course_level_progression": 1.0,
        "gpa_risk": 0.75
      },
      "reason_codes": ["ai_infra_match", "prerequisites_satisfied"],
      "notes": []
    }
  ],
  "notes": [
    "Scores are internal debug signals and should not be shown in normal UI.",
    "Courses without matching career tags are excluded in this first version."
  ]
}
```

### `search_course_docs`

Status: Implemented

Purpose:

Wrap the DB-aware keyword retriever as an explicit tool. This is the stable contract used by the tool router (and later, LLM function calling). Retrieval-algorithm details live in `services/rag/retriever.py`; the tool layer only exposes schema, validation, and course-ID normalization so the underlying retriever can be swapped for pgvector semantic search later without changing callers.

Input:

```json
{
  "query": "What is ECE 408 about GPU programming?",
  "course_ids": ["ece408"],
  "top_k": 3
}
```

Behavior:

- `query` must be non-empty (whitespace-only rejected).
- `top_k` must be in `[1, 20]`.
- `course_ids` (optional) are normalized via `normalize_course_id` and deduplicated.
- Retrieval first tries the `courses` table; falls back to sample chunks if the DB has no match.
- `notes` surfaces empty-result and fallback conditions so the tool router / LLM can respond safely instead of hallucinating.

Output:

```json
{
  "query": "What is ECE 408 about GPU programming?",
  "course_ids": ["ECE 408"],
  "docs": [
    {
      "course_id": "ECE 408",
      "source_name": "Course Database",
      "source_url": "https://ece.illinois.edu/academics/courses",
      "section_type": "course_profile",
      "snippet": "ECE 408: Applied Parallel Programming ...",
      "score": 0.42
    }
  ],
  "notes": []
}
```

### Manual tool router

Status: Implemented

Purpose:

Turn a raw user query into a structured `ToolPlan` — an intent label, extracted parameters, and an ordered list of `ToolCall` objects. The router is deterministic and rule-based. It runs before any LLM call and gates which tools the advising service will actually invoke. This matches SOP §9.4 v1 (rule-based intent detection); an LLM planner fallback is deferred to v2 once vLLM is wired in.

Intents:

- `course_qa`
- `comparison`
- `recommendation`
- `prereq_check`

Priority order (first match wins):

1. Prereq keywords (`prereq`, `ready for`, `can i take`, `am i ready`) + at least one course id → `prereq_check`
2. Recommend keywords (`recommend`, `what should i take`, `good for`, `useful for`, `courses for`) → `recommendation`
3. Compare keywords (`compare`, `vs`, `versus`, `difference between`) OR two or more course ids → `comparison`
4. Otherwise → `course_qa`

Downgrade rules protect the pipeline from underspecified queries:

- `prereq_check` with no course id → downgrades to `course_qa` and records a `notes` entry.
- `comparison` with only one course id → downgrades to `course_qa` and records a `notes` entry.
- `recommendation` with no detectable direction → stays `recommendation` but sets `target_direction=None` and records a `notes` entry so the LLM asks the user for a direction instead of guessing.

Direction extraction uses a small ordered phrase → career-tag map (longer phrases first) so `"ai infrastructure"` beats `"ai"`. Career tags line up with `career_tags` used by `recommend_courses`.

Input:

```python
plan_tools("Compare ECE 408 and CS 433 for AI infra", completed_courses=["ECE 220"])
```

Output (`ToolPlan`):

```json
{
  "intent": "comparison",
  "course_ids": ["ECE 408", "CS 433"],
  "target_direction": "ai_infra",
  "completed_courses": ["ECE 220"],
  "tool_calls": [
    {"tool_name": "get_course_profile", "arguments": {"course_id": "ECE 408"}},
    {"tool_name": "get_course_profile", "arguments": {"course_id": "CS 433"}},
    {"tool_name": "get_gpa_stats",      "arguments": {"course_id": "ECE 408"}},
    {"tool_name": "get_gpa_stats",      "arguments": {"course_id": "CS 433"}},
    {"tool_name": "compare_courses",    "arguments": {"course_ids": ["ECE 408", "CS 433"], "dimension": "ai_infra", "completed_courses": ["ECE 220"]}}
  ],
  "notes": []
}
```

### Debug tool trace

Status: Implemented

Purpose:

`ToolTraceCollector` is the single source of truth for what tools ran on a request, in what order, with what arguments, how long each took, and whether it succeeded. The collector is populated on every request; the serialized `DebugTrace` is only attached to the response when `debug=true`. The same collector will later feed Prometheus metrics and structured logs (Phase E), so instrumentation is not duplicated.

Design:

- `collector.time_tool(name, args)` is a context manager that starts a timer, yields a `ToolSpan` (call `span.set_result_summary(...)` for small metadata), auto-appends a `ToolCallTrace` on exit, and on exception records `status="error"` + error message before re-raising.
- `collector.record_skipped_tool(name, args, reason)` records tools intentionally skipped (e.g., comparison downgrade with only one course id).
- `collector.record_chunks(...)` / `record_recommendation_scores(...)` capture large payloads separately from the tool-call summary so per-call `result_summary` stays small.
- `collector.tool_names()` powers `ChatResponse.used_tools` — that field is now derived, not hardcoded.
- `collector.to_debug_trace()` serializes to the `DebugTrace` Pydantic model.

Tool-call entry shape:

```json
{
  "tool_name": "get_course_profile",
  "arguments": {"course_id": "ECE 391"},
  "status": "success",
  "latency_ms": 2,
  "error": null,
  "result_summary": {"found": true, "title": "Computer Systems Engineering"}
}
```

### Tool dispatcher

Status: Implemented

Purpose:

Execute the ordered `tool_calls` on a `ToolPlan` against real tool functions. The dispatcher is the seam between the deterministic router (produces a plan) and the actual side-effectful tools (query the DB, run scoring). It is where per-tool timing, error isolation, and result aggregation live.

Design:

- One entry per tool_name via explicit `if/elif` (no dynamic dispatch — clearer failure modes, easier grep).
- Each branch wraps its tool call in `collector.time_tool(name, args)`, giving uniform latency + status recording for free.
- **Error isolation**: dispatcher catches `Exception` around each branch and continues — the collector already records `status="error"` + error message. One failing tool does not abort the request; the answer synthesizer sees whichever `DispatchedResults` fields did get populated and either grounds on them or falls back.
- `recommend_courses` with a `None` target_direction is proactively recorded as `skipped` before the tool call so the underlying `ValueError` never fires.
- Unknown `tool_name` values are recorded as `skipped` rather than raised, so a bad router entry logs cleanly instead of crashing the request.
- Chunks from `search_course_docs` are pushed into `collector.record_chunks`; recommendation output into `collector.record_recommendation_scores`. Per-tool `result_summary` stays small (booleans, counts, titles) so the debug payload does not balloon.

Output aggregate (`DispatchedResults`):

```python
@dataclass
class DispatchedResults:
    course_profiles: dict[str, CourseProfile | None]
    gpa_stats:       dict[str, GPAStats | None]
    prereq_checks:   dict[str, PrerequisiteCheck | None]
    comparison:      CourseComparison | None
    recommendations: CourseRecommendations | None
    search_result:   SearchCourseDocsResult | None
```

### Answer synthesis (template)

Status: Implemented (template only)

Purpose:

Turn `DispatchedResults` into a natural-language answer per intent. This is still template-based (string joins over tool output) — every branch ends with `TODO: replace this template with LLM evidence synthesis after vLLM integration`. The four intents each have an "evidence-grounded" branch and a "no-evidence fallback" branch (safe "I could not find enough evidence..." message).

## Planned

- LLM planner fallback (v2, after vLLM is wired up) for queries the rule-based router cannot classify confidently.
- Prometheus metrics exporter reading from the trace collector (Phase E).
- Replace `answer_synthesis.build_answer` template with vLLM-backed LLM synthesis (Phase C).
- Wire `/api/compare` and `/api/recommend` to the same pipeline (currently still mocked).

## Design Rule

Route handlers should not call the database directly for course facts. They should call services/tools that can be tested independently.
