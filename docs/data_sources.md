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
- The parser and ingestion seam accept `--limit` for bounded development runs;
  omitting it ingests every parsed row from the source page.
- The source URL is stored on each `courses` row.
- The script is re-runnable and updates existing course title/prerequisite fields.
- The first real run ingested 20 source-tagged ECE course rows.
- The local development database was later expanded to 80 ECE course rows so upper-level systems and AI infrastructure courses such as `ECE 408` and `ECE 411` are available for tool testing.

Run a bounded local development slice:

```bash
cd backend
.venv/bin/python -m scripts.ingest_ece_prereqs --limit 20
```

Run a full ECE source ingestion (this is a live-network/database operation):

```bash
cd backend
.venv/bin/python -m scripts.ingest_ece_prereqs
```

Each live invocation writes a machine-readable manifest under
`artifacts/ingestion/<run-id>/manifest.json`. It contains the source URL,
UTC fetch timestamp, and parsed/inserted/updated/skipped/duplicate counts for
that department. No runtime artifact is committed as project evidence.

This source is used for ECE course titles and prerequisite text. It does not yet parse prerequisite logic into a graph.

## CS Course Catalog

Status: Implemented; live validation pending

Source page:

```text
https://catalog.illinois.edu/courses-of-instruction/cs/
```

Current ingestion boundary:

- The parser accepts only CS course headings with a valid `CS <number>` identity.
- It stores the official catalog URL on every inserted or updated `courses` row.
- Prerequisites are stored as source text; malformed or absent prerequisite text
  does not abort the run and is not yet converted into a prerequisite graph.
- Re-running the same source upserts existing courses rather than adding duplicate
  rows. Duplicate course identities within one source response are counted in the
  runtime manifest.

Run a bounded local development slice:

```bash
cd backend
.venv/bin/python -m scripts.ingest_cs_courses --limit 20
```

Run the full CS source ingestion:

```bash
cd backend
.venv/bin/python -m scripts.ingest_cs_courses
```

The CS catalog parser is tested only against a saved HTML fixture. A successful
live command is required before claiming any CS course count, combined ECE+CS
count, or the resume target of 150+ source-tagged courses.

## Combined ECE + CS Coverage Gate

Status: Implemented; live validation pending

Run both official catalog ingestions in one database session and write one
combined manifest:

```bash
cd backend
.venv/bin/python -m scripts.ingest_course_catalogs --require-minimum-distinct 150
```

The manifest includes two department entries and
`total_distinct_course_count`, queried after both upserts using distinct
`course_id` values restricted to ECE and CS. Run this against the intended
clean evaluation database when using it as evidence for the 150+ resume gate;
the count otherwise includes pre-existing ECE/CS course rows in that database.

For a bounded parser/DB smoke test, use separate explicit limits:

```bash
cd backend
.venv/bin/python -m scripts.ingest_course_catalogs --ece-limit 20 --cs-limit 20
```

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

Current local development result after expanding ECE ingestion to 80 rows:

```text
Seeded career tags for 11/12 configured courses. Missing courses: ECE 419.
```

This enables `recommend_courses("ai_infra")` to return tagged courses such as `ECE 408` and `ECE 411` in the local development database.

Rules:

- The seed only updates courses already present in the `courses` table.
- It does not create fake course records.
- It is re-runnable.
- These tags are project annotations, not official UIUC metadata.
- Recommendation results should mention that tags are a first-version manual signal when shown in debug or documentation.
