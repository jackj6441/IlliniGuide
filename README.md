# IlliniGuide Serve

IlliniGuide Serve is a self-hosted LLM/RAG serving platform for UIUC ECE/CS academic advising workloads.

The project is framed as an AI infrastructure and LLM serving system, not a simple chatbot. The advising workflow is the demo workload; the core technical focus is structured retrieval, tool orchestration, citation grounding, observability, evaluation, and eventually Kubernetes reliability experiments.

## Project Documents

- [PROJECT_SOP.md](PROJECT_SOP.md): full project SOP, roadmap, architecture, API design, data model, evaluation plan, and execution plan.
- [AGENTS.md](AGENTS.md): collaboration rules for tutor-first implementation, testing, documentation, and interview readiness.
- [docs/architecture.md](docs/architecture.md): current architecture status and planned module boundaries.
- [docs/data_sources.md](docs/data_sources.md): current real-data sources and ingestion boundaries.
- [docs/rag_design.md](docs/rag_design.md): current mock RAG design and planned retrieval pipeline.
- [docs/tool_calling_design.md](docs/tool_calling_design.md): current structured tool design and planned tool router.
- [docs/demo_script.md](docs/demo_script.md): demo flow, with implementation status tracked honestly.

## Target Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, Python 3.11+, Pydantic, SQLAlchemy or SQLModel
- Database: PostgreSQL with pgvector
- LLM serving: vLLM OpenAI-compatible endpoint
- Observability: Prometheus and Grafana
- Deployment: Docker Compose first, Kubernetes later

## First Implementation Phase

Start with the local MVP:

1. Initialize repository structure. Status: Implemented.
2. Build FastAPI backend skeleton. Status: Implemented with mocked services.
3. Add `/health`, `/api/chat`, `/api/compare`, and `/api/recommend`. Status: Implemented with mocked responses.
4. Add PostgreSQL and pgvector setup.
5. Implement database models. Status: Implemented.
6. Add mock keyword-based RAG over sample course data. Status: Implemented.
7. Build frontend MVP with chat, comparison, citations, and debug trace.

## Current Status

| Feature | Status | Notes |
|---|---|---|
| Project SOP | Implemented | See `PROJECT_SOP.md`. |
| Agent collaboration rules | Implemented | See `AGENTS.md`. |
| Repository skeleton | Implemented | Top-level `backend/`, `frontend/`, `docs/`, `eval/`, and `infra/` directories exist. |
| PostgreSQL Compose service | Implemented | `docker-compose.yml` defines a pgvector-backed PostgreSQL service. |
| FastAPI backend skeleton | Implemented | Routes exist with mocked service responses. |
| Database models | Implemented | SQLAlchemy models exist for courses, instructors, GPA stats, chunks, and eval logs. |
| Database initialization | Implemented | `scripts.init_db` creates the pgvector extension and current tables. |
| GPA ingestion | Implemented | Bounded WAF GPA CSV ingestion, default limit 20 ECE/CS rows. |
| ECE prerequisite ingestion | Implemented | Bounded official ECE courses ingestion, default limit 20 rows. |
| DB-aware mock RAG | Implemented | Keyword retrieval over course DB rows, with sample chunk fallback. |
| `get_course_profile` tool | Implemented | Structured lookup from `courses` table. |
| `get_gpa_stats` tool | Implemented | Structured lookup and aggregation from `gpa_stats` rows. |
| `check_prerequisites` tool | Implemented | Course-ID prerequisite readiness check from official ECE prerequisite text. |
| `compare_courses` tool | Implemented | Structured comparison object over course profiles, GPA, prerequisites, and direction tags. |
| `recommend_courses` tool | Implemented | Rule-based recommendations with internal score breakdown for debug/API use. |
| React frontend | Planned | Will start after backend skeleton and mocked APIs. |
| Real RAG pipeline | Planned | pgvector retrieval, ingestion, embeddings, and fallback are not implemented yet. |
| vLLM integration | Planned | Later Phase 1/2 serving work. |

## Local Development

Create a local environment file from the template:

```bash
cp .env.example .env
```

Start the database:

```bash
docker compose up postgres
```

Initialize database tables:

```bash
cd backend
.venv/bin/python -m scripts.init_db
```

Ingest 20 GPA/instructor rows from the WAF Grade Disparities source:

```bash
cd backend
.venv/bin/python -m scripts.ingest_gpa --limit 20
```

Ingest 20 ECE course prerequisite rows from the official ECE courses page:

```bash
cd backend
.venv/bin/python -m scripts.ingest_ece_prereqs --limit 20
```

The application backend and frontend are not implemented yet.

Run backend tests:

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Start the mocked backend:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload
```

The backend currently returns mocked advising responses. Some database-backed services and tools are implemented, but real API-level tool routing, embedding RAG, and LLM calls are planned.

## Core Design Rule

The LLM should act as the intent understanding, planning, and explanation layer. Reliable facts, prerequisite checks, GPA lookup, retrieval, and recommendation scores should come from structured tools.
