# IlliniGuide Serve

IlliniGuide Serve is a self-hosted LLM/RAG serving platform for UIUC ECE/CS academic advising workloads.

The project is framed as an AI infrastructure and LLM serving system, not a simple chatbot. The advising workflow is the demo workload; the core technical focus is structured retrieval, tool orchestration, citation grounding, observability, evaluation, and eventually Kubernetes reliability experiments.

## Project Documents

- [PROJECT_SOP.md](PROJECT_SOP.md): full project SOP, roadmap, architecture, API design, data model, evaluation plan, and execution plan.
- [AGENTS.md](AGENTS.md): collaboration rules for tutor-first implementation, testing, documentation, and interview readiness.
- [docs/architecture.md](docs/architecture.md): current architecture, implemented boundaries, and remaining gaps.
- [docs/data_sources.md](docs/data_sources.md): current real-data sources and ingestion boundaries.
- [docs/rag_design.md](docs/rag_design.md): section chunking, embeddings, pgvector retrieval, fallback behavior, and the remaining evaluation gap.
- [docs/tool_calling_design.md](docs/tool_calling_design.md): current structured tool design and planned tool router.
- [docs/llm_serving_design.md](docs/llm_serving_design.md): LLM client abstraction, self-hosted vLLM design, and serving tradeoffs.
- [docs/vllm_setup.md](docs/vllm_setup.md): step-by-step manual for launching vLLM on the ICRN H200 and wiring the backend to it.
- [docs/postgres_icrn_setup.md](docs/postgres_icrn_setup.md): step-by-step manual for installing PostgreSQL + pgvector on ICRN via conda (no docker, no sudo), initializing tables, and ingesting real UIUC data.
- [docs/interview_notes_vllm.md](docs/interview_notes_vllm.md): resume bullet, 60-second pitch, and three-level Q&A for the LLM serving portion. Numbers filled from `scripts/benchmark.py`.
- [docs/demo_script.md](docs/demo_script.md): demo flow, with implementation status tracked honestly.
- [docs/todo_roadmap.md](docs/todo_roadmap.md): evidence-gated roadmap for RAG evaluation, observability, reproducible benchmarking, Docker, and Kubernetes.
- [docs/multi_agent_delivery_plan.md](docs/multi_agent_delivery_plan.md): dependency-aware multi-agent ownership and delivery sequence for that roadmap.

## Technology Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, Python 3.11+, Pydantic, SQLAlchemy
- Database: PostgreSQL with pgvector
- LLM serving: vLLM OpenAI-compatible endpoint
- Observability target: application metrics plus Prometheus and Grafana
- Deployment path: Docker Compose verification first, Kubernetes later

## Delivery History

The project started as a local MVP and has progressed into a demonstrable AI-serving prototype:

1. Initialize repository structure. Status: Implemented.
2. Build the FastAPI route/service boundary and API schemas. Status: Implemented.
3. Add `/health`, `/api/chat`, `/api/chat/stream`, `/api/compare`, and `/api/recommend`. Status: Implemented.
4. Add PostgreSQL and pgvector setup. Status: Implemented.
5. Implement database models. Status: Implemented.
6. Add structured tools and route chat through router, dispatcher, and answer synthesis. Status: Implemented.
7. Add semantic pgvector retrieval and embedding ingestion. Status: Partial; code exists, but live quality evaluation is still missing.
8. Serve Qwen2.5-7B-Instruct through vLLM on ICRN H200 and add SSE streaming. Status: Implemented.
9. Build the React chat, comparison, and recommendation UI. Status: Implemented; the production build has passed.

## Current Status

| Feature | Status | Notes |
|---|---|---|
| FastAPI and service layering | Implemented | Thin routes call advising services, which coordinate the manual router, error-isolated dispatcher, structured tools, and LLM answer synthesis. Backend tests previously passed: `223 passed`. |
| Structured academic tools | Implemented | Course profile, GPA, prerequisites, comparison, recommendation, and document search have explicit implementations and tests. |
| PostgreSQL + pgvector schema | Implemented | Structured course/GPA tables, vector chunks, and evaluation tables are initialized by the database layer. |
| Data ingestion | Partial | The evidenced local dataset contains 80 ECE courses and 20 GPA rows; CS/catalog coverage and career tags are not yet complete. |
| Semantic RAG | Partial | Section chunking, MiniLM embeddings, pgvector cosine search, course filtering, keyword fallback, and low-confidence notes exist. A live, labeled retrieval-quality report is still missing. |
| Self-hosted vLLM | Implemented | The verified baseline is Qwen2.5-7B-Instruct, FP16, 8K context, served through vLLM on an ICRN H200 with prefix caching. Qwen3-32B BF16 is a target, not a current result. |
| Streaming | Implemented | `POST /api/chat/stream` emits SSE content and metadata; the React client parses the stream, renders incrementally, and supports cancellation. The frontend production build previously passed. |
| Benchmark | Partial | Historical notes record streaming p50 client-observed TTFT 55 ms and blocking p50 full-response latency 472 ms at concurrency 10, with 47 counted requests per run. See the exact command shape and evidence limits in `docs/llm_serving_design.md`; saved evidence does not yet establish tokens/sec, error rate, or GPU compute utilization. |
| Observability | Partial | Per-tool trace and a vLLM `/metrics` snapshot script exist; Prometheus scraping, Grafana dashboards, and application-level metrics are not yet verified. |
| Evaluation | Partial | Retrieval evaluation code exists, but there is no frozen 30–50-query advisor set or saved quality report. No 92% relevance claim is currently supported. |
| Docker | Partial | Backend/frontend image files are WIP in the working tree; a clean Compose smoke test has not been recorded. |
| Kubernetes | Planned | `infra/k8s/` has no manifests or rollout/recovery evidence. |

Resume and status claims are evidence-gated. Qwen3-32B BF16, 150+ indexed courses, 92% relevance, and 65–70% GPU utilization remain targets until the artifacts required by [the roadmap](docs/todo_roadmap.md) are captured.

## Running the Serving Stack on ICRN (One Command)

After the one-time setup in `docs/postgres_icrn_setup.md` and `docs/vllm_setup.md`:

```bash
cd ~/IlliniGuide
bash scripts/dev_up.sh
```

That script starts PostgreSQL, vLLM (Qwen2.5-7B-Instruct), and the FastAPI backend in the right order, waits for each to be ready before starting the next, and streams each service's logs to `/tmp/*.log`. All three run in the background from a single terminal.

The React frontend is started separately; this command covers the serving stack, not the browser development server.

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

The backend and React frontend are implemented. Local development can use the deterministic mock LLM, while the evidenced self-hosted path points the backend at the ICRN vLLM endpoint.

Run backend tests:

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Start the backend (the default local configuration uses the mock LLM unless `LLM_BACKEND` is overridden):

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload
```

The same route/service pipeline is used for mock and self-hosted inference. Select `LLM_BACKEND=vllm_remote` and follow `docs/vllm_setup.md` to use the verified Qwen2.5-7B-Instruct endpoint. Semantic retrieval requires persisted embeddings; follow `docs/rag_design.md` and keep its quality status Partial until a live evaluation artifact exists.

## Core Design Rule

The LLM should act as the intent understanding, planning, and explanation layer. Reliable facts, prerequisite checks, GPA lookup, retrieval, and recommendation scores should come from structured tools.
