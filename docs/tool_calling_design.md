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

## Planned

- `search_course_docs`
- `get_gpa_stats`
- `check_prerequisites`
- `compare_courses`
- `recommend_courses`
- Manual tool router
- Debug tool trace

## Design Rule

Route handlers should not call the database directly for course facts. They should call services/tools that can be tested independently.
