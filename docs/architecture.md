# Architecture

Status: Partial

This document tracks the architecture as it becomes implemented. It must distinguish implemented behavior from planned behavior.

## Implemented

- Repository-level project documents:
  - `README.md`
  - `PROJECT_SOP.md`
  - `AGENTS.md`
- Initial project directories:
  - `backend/`
  - `frontend/`
  - `docs/`
  - `eval/`
  - `infra/`
- Local PostgreSQL + pgvector Docker Compose service definition.
- FastAPI backend skeleton:
  - `GET /health`
  - `POST /api/chat`
  - `POST /api/compare`
  - `POST /api/recommend`
- Pydantic request/response schemas for the initial API contract.
- Mock advising service used to unblock frontend development.
- SQLAlchemy database models for:
  - `courses`
  - `instructors`
  - `gpa_stats`
  - `course_chunks`
  - `eval_runs`
  - `eval_results`
- Database initialization script for pgvector extension and current tables.

## Planned

- Service-layer RAG and tool orchestration.
- Alembic migrations.
- Real PostgreSQL connection tests.
- React frontend for chat and course comparison.
- vLLM-compatible LLM client abstraction.
- Prometheus/Grafana observability.
- Evaluation and benchmark reports.

## Current Boundary

The current backend behavior is mocked. It validates request/response shapes and route structure, but it does not yet query PostgreSQL, retrieve embeddings, call vLLM, or run real tools.

Future backend code should follow this boundary:

```text
api/ = HTTP route layer
services/ = business logic
db/ = database models and sessions
ingestion/ = data loading pipelines
evaluation/ = evaluation runner and metrics
```

Current backend boundary:

```text
backend/app/api/ = thin FastAPI route handlers
backend/app/services/ = mocked advising service
backend/app/schemas.py = Pydantic API contracts
backend/tests/ = API response shape tests
```
