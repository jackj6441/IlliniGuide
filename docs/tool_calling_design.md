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

## Planned

- `search_course_docs`
- `check_prerequisites`
- `compare_courses`
- `recommend_courses`
- Manual tool router
- Debug tool trace

## Design Rule

Route handlers should not call the database directly for course facts. They should call services/tools that can be tested independently.
