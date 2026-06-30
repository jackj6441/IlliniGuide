# Data Schema

Status: Partial

The backend now defines SQLAlchemy models for the core database schema. The models match the first database scope in `PROJECT_SOP.md`.

## Implemented Models

| Table | Status | Purpose |
|---|---|---|
| `courses` | Implemented | Structured course facts such as title, description, prerequisites, source URL, and career tags. |
| `instructors` | Implemented | Instructor identity table. |
| `gpa_stats` | Implemented | Course/instructor/term GPA evidence and grade distributions. |
| `course_chunks` | Implemented | Citation-bearing document chunks with pgvector embeddings. |
| `eval_runs` | Implemented | Evaluation run metadata. |
| `eval_results` | Implemented | Per-question evaluation outputs, retrieved evidence, scores, and latency. |

## Planned

- Alembic migrations.
- PostgreSQL integration test using Docker Compose.
- pgvector extension initialization script.
- Repository/query layer for course lookup and retrieval.

## Design Notes

Structured course facts and vector chunks are separate on purpose:

- `courses` and `gpa_stats` answer factual questions with reliable structured data.
- `course_chunks` supports semantic retrieval and citation grounding.
- `eval_runs` and `eval_results` make correctness, citation quality, and latency measurable.

The `course_chunks.embedding` column uses `pgvector.sqlalchemy.Vector`, which compiles to PostgreSQL `VECTOR`.
