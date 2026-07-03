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
- [docs/llm_serving_design.md](docs/llm_serving_design.md): LLM client abstraction, vLLM concepts, and Phase C roadmap.
- [docs/vllm_setup.md](docs/vllm_setup.md): step-by-step manual for launching vLLM on the ICRN H200 and wiring the backend to it.
- [docs/postgres_icrn_setup.md](docs/postgres_icrn_setup.md): step-by-step manual for installing PostgreSQL + pgvector on ICRN via conda (no docker, no sudo), initializing tables, and ingesting real UIUC data.
- [docs/interview_notes_vllm.md](docs/interview_notes_vllm.md): resume bullet, 60-second pitch, and three-level Q&A for the LLM serving portion. Numbers filled from `scripts/benchmark.py`.
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
| Career tag seed | Implemented | Reproducible manual tags for selected core courses; only updates courses already in DB. |
| DB-aware mock RAG | Implemented | Keyword retrieval over course DB rows, with sample chunk fallback. |
| `get_course_profile` tool | Implemented | Structured lookup from `courses` table. |
| `get_gpa_stats` tool | Implemented | Structured lookup and aggregation from `gpa_stats` rows. |
| `check_prerequisites` tool | Implemented | Course-ID prerequisite readiness check from official ECE prerequisite text. |
| `compare_courses` tool | Implemented | Structured comparison object over course profiles, GPA, prerequisites, and direction tags. |
| `recommend_courses` tool | Implemented | Rule-based recommendations with internal score breakdown for debug/API use. |
| `search_course_docs` tool | Implemented | Explicit-schema wrapper around the DB-aware keyword retriever, with course-ID normalization and safe empty/fallback notes. |
| Manual tool router | Implemented | Rule-based intent detection (`course_qa`/`comparison`/`recommendation`/`prereq_check`) producing a `ToolPlan` with an ordered `ToolCall` sequence. |
| Debug tool trace | Implemented | `ToolTraceCollector` records per-tool arguments, latency, status, and result summary; serialized to `debug_trace` when `debug=true`. Same collector will feed Prometheus in Phase E. |
| `/api/chat` real tool pipeline | Implemented | Router → dispatcher → real tool execution → template answer synthesis. Per-tool errors are isolated; LLM synthesis still template-based (replaced in vLLM phase). |
| LLM client abstraction | Implemented | `services/llm/` — `LLMClient` Protocol, `MockLLMClient` (deterministic), `create_llm_client()` factory reading `LLM_BACKEND` env. `vllm_remote` / `external_debug` backends planned (Task C3). |
| `/api/chat` LLM synthesis | Implemented | Per-intent prompt templates + async `build_answer` calling `LLMClient`. LLM errors record `status="error"` and fall back to deterministic template. `used_tools` ends with `llm_generate`. |
| `vllm_remote` / `external_debug` backends | Implemented | `VLLMRemoteClient` (httpx.AsyncClient over `/v1/chat/completions`) with exponential-backoff retry on network/5xx, no retry on 4xx. Same class serves both backends; env resolution differs. |
| vLLM launch on ICRN H200 | Implemented | Qwen2.5-7B-Instruct running self-hosted on ICRN H200 (141 GB VRAM). First measured: LLM call 231 ms wall, avg TTFT 506 ms over first 2 requests. `debug_trace.tool_calls[-1].arguments.backend == "vllm_remote"` on real `/api/chat`. |
| Streaming `/api/chat/stream` | Implemented (backend) | SSE endpoint with content-then-metadata events. `LLMClient.stream_generate` on both mock and vLLM backends; graceful degradation to template on pre-first-chunk error, honest truncation on mid-stream error. Frontend `EventSource` client is Phase B. |
| Benchmark harness + interview notes | Manual — awaiting execution | `scripts/benchmark.py` reports per-request TTFT (streaming) vs total latency and p50/p95/p99 across both chat endpoints under configurable concurrency; `docs/interview_notes_vllm.md` holds the resume bullet, 60-sec pitch, and 15 Q&A (numbers filled in from actual ICRN runs). |
| React frontend | Planned | Will start after backend skeleton and mocked APIs. |
| Real RAG pipeline | Planned | pgvector retrieval, ingestion, embeddings, and fallback are not implemented yet. |
| vLLM integration | Planned | Later Phase 1/2 serving work. |

## Running the Whole Stack on ICRN (One Command)

After the one-time setup in `docs/postgres_icrn_setup.md` and `docs/vllm_setup.md`:

```bash
cd ~/IlliniGuide
bash scripts/dev_up.sh
```

That script starts PostgreSQL, vLLM (Qwen2.5-7B-Instruct), and the FastAPI backend in the right order, waits for each to be ready before starting the next, and streams each service's logs to `/tmp/*.log`. All three run in the background from a single terminal.

Stop everything with:

```bash
bash scripts/dev_down.sh
```

Logs live at `/tmp/vllm.log`, `/tmp/backend.log`, and `$PGDATA/server.log`. `tail -f` each to watch a specific service.

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

Seed manual career tags for already-ingested core courses:

```bash
cd backend
.venv/bin/python -m scripts.seed_career_tags
```

The initial 20-row ECE ingestion may not include upper-level tagged courses such as `ECE 408`. Expand the ECE ingestion limit before seeding tags when you are ready to broaden the dataset.

The current local development database has been expanded to 80 ECE rows and career tags were seeded for 11 configured core courses.

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
