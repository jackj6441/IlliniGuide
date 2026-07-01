# Data Sources

Status: Partial

## WAF Grade Disparities and Accolades

Status: Implemented for bounded ingestion

Source page:

```text
https://waf.cs.illinois.edu/visualizations/Grade-Disparities-and-Accolades-by-Instructor/
```

CSV source used by the page:

```text
https://waf.cs.illinois.edu/visualizations/Grade-Disparities-and-Accolades-by-Instructor/final.csv
```

Current ingestion boundary:

- Only ECE and CS rows are considered.
- Default limit is 20 GPA/instructor/course rows.
- The source URL is stored on each `gpa_stats` row.
- The script is re-runnable and avoids duplicate GPA rows for the same course, instructor, term, and source URL.
- The first real run ingested 20 source-tagged GPA rows after scanning 2711 CSV rows.

Run:

```bash
cd backend
.venv/bin/python -m scripts.ingest_gpa --limit 20
```

This source is used only for GPA/instructor evidence. It is not the official course catalog and should not be used as the authority for requirements or prerequisites.

## ECE Courses and Prerequisites

Status: Implemented for bounded ingestion

Source page:

```text
https://ece.illinois.edu/academics/courses
```

Current ingestion boundary:

- Only ECE course rows from the official ECE page are considered.
- Default limit is 20 unique course rows.
- The source URL is stored on each `courses` row.
- The script is re-runnable and updates existing course title/prerequisite fields.
- The first real run ingested 20 source-tagged ECE course rows.

Run:

```bash
cd backend
.venv/bin/python -m scripts.ingest_ece_prereqs --limit 20
```

This source is used for ECE course titles and prerequisite text. It does not yet parse prerequisite logic into a graph.

## Manual Career Tags

Status: Implemented for selected core courses

Career tags are manually curated labels used by the first version of `recommend_courses`.

Current tags include examples such as:

```text
ai_infra
ai_ml
systems
software_engineering
computer_architecture
data_science
robotics_cv
security
```

Run:

```bash
cd backend
.venv/bin/python -m scripts.seed_career_tags
```

For the AI infrastructure tags to attach, the `courses` table must already contain the configured upper-level courses. With the initial 20-row ECE ingestion, many of these courses are not present yet. Expand the ECE ingestion limit first when you are ready to broaden the dataset:

```bash
cd backend
.venv/bin/python -m scripts.ingest_ece_prereqs --limit 80
.venv/bin/python -m scripts.seed_career_tags
```

Rules:

- The seed only updates courses already present in the `courses` table.
- It does not create fake course records.
- It is re-runnable.
- These tags are project annotations, not official UIUC metadata.
- Recommendation results should mention that tags are a first-version manual signal when shown in debug or documentation.
