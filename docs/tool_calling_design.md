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

## Planned

- `search_course_docs`
- `compare_courses`
- `recommend_courses`
- Manual tool router
- Debug tool trace

## Design Rule

Route handlers should not call the database directly for course facts. They should call services/tools that can be tested independently.
