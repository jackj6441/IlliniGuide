# Architecture

Status: Partial

IlliniGuide Serve is a demonstrable AI-serving prototype. The request path, structured tools, self-hosted vLLM integration, and frontend streaming are implemented; evaluation, observability, container verification, and Kubernetes reliability remain incomplete.

See [todo_roadmap.md](todo_roadmap.md) for the evidence gates and [multi_agent_delivery_plan.md](multi_agent_delivery_plan.md) for file ownership and execution order.

## Request Path

```text
React UI
  -> FastAPI route (`api/`)
  -> advising service
  -> rule-based tool router
  -> error-isolated tool dispatcher
  -> structured tools + PostgreSQL/pgvector retrieval
  -> LLM answer synthesis through the unified client
  -> blocking JSON or streaming SSE response
```

The route layer owns HTTP parsing and response types. Business orchestration stays in `services/`; database models and sessions stay in `db/`; source ingestion stays in `ingestion/`. This separation lets tool, retrieval, and synthesis behavior be tested without putting business logic inside FastAPI handlers.

## Current Status

| Area | Status | Current boundary |
|---|---|---|
| FastAPI route/service layering | Implemented | `/health`, chat, streaming chat, compare, and recommend routes call service-layer logic. The backend suite previously passed `223` tests. |
| Tool orchestration | Implemented | `plan_tools` produces an ordered plan; `execute_plan` calls explicit tools and isolates individual failures; answer synthesis consumes the dispatched evidence. |
| Structured tools | Implemented | Course profile, GPA, prerequisite, comparison, recommendation, and document-search tools query deterministic data instead of asking the LLM to invent facts. |
| PostgreSQL + pgvector | Implemented | Models and initialization exist for courses, instructors, GPA statistics, vector chunks, and evaluation records. |
| Data corpus | Partial | The evidenced local baseline is 80 ECE courses and 20 GPA rows. CS/catalog coverage and career tags remain incomplete. |
| Semantic RAG | Partial | Section chunking, 384-dimensional MiniLM embeddings, pgvector cosine search, course metadata filtering, keyword fallback, and a low-confidence note are implemented in code. A real labeled retrieval report is still missing. |
| LLM client abstraction | Implemented | `mock`, `vllm_remote`, and `external_debug` backends are separated behind one client interface. The external backend is only a debug fallback. |
| Self-hosted inference | Implemented | The verified baseline is Qwen2.5-7B-Instruct, FP16, 8K context, served through vLLM on an ICRN H200 with prefix caching. |
| Streaming | Implemented | The backend emits content and metadata SSE events. The React client parses them, renders incrementally, and supports cancellation; its production build previously passed. |
| Benchmarking | Partial | The harness measures streaming TTFT and total latency. Historical notes record streaming p50 client-observed TTFT 55 ms and blocking p50 full-response latency 472 ms at concurrency 10, with 47 counted requests per run; exact command shape and limitations are documented in `llm_serving_design.md`. Saved tokens/sec, error-rate, and GPU-utilization results do not yet exist. |
| Observability | Partial | Per-tool debug trace and a vLLM `/metrics` snapshot script exist. Application metrics, Prometheus scraping, and Grafana dashboards are not yet verified. |
| Evaluation | Partial | Retrieval evaluation code exists, but the frozen 30–50-query advisor set and saved result report do not. |
| Docker | Partial | Backend and frontend image files are WIP in the working tree; a clean Compose smoke test has not been recorded. |
| Kubernetes | Planned | No manifests, rollout test, or pod-recovery evidence exists. |

## Implemented Components

### API and service layer

- `backend/app/api/`: thin FastAPI route handlers.
- `backend/app/services/advising_service.py`: coordinates routing, tool execution, synthesis, tracing, and streaming.
- `backend/app/services/tools/router.py`: deterministic intent detection and `ToolPlan` creation.
- `backend/app/services/tools/dispatcher.py`: explicit tool execution with per-tool failure isolation.
- `backend/app/services/tools/trace.py`: per-tool arguments, latency, status, and result summaries for debug responses.
- `backend/app/services/answer_synthesis.py`: prompt-driven LLM synthesis with deterministic fallback when generation fails before output begins.

### Data and retrieval layer

- SQLAlchemy models for `courses`, `instructors`, `gpa_stats`, `course_chunks`, `eval_runs`, and `eval_results`.
- Bounded GPA and ECE ingestion plus reproducible career-tag seeding.
- Section-aware course chunking and embedding persistence.
- Semantic pgvector search with course filters, keyword fallback, and citation-oriented retrieval results.

The retriever code being present does not prove retrieval quality. Semantic RAG remains Partial until a real database run produces a versioned, labeled evaluation artifact.

### LLM serving and streaming

- `LLMClient` abstraction with deterministic mock, self-hosted `vllm_remote`, and isolated `external_debug` configurations.
- OpenAI-compatible `/v1/chat/completions` integration with retry rules for non-streaming network/5xx failures.
- Streaming deliberately avoids automatic retry because retrying after partial output could duplicate or corrupt the response.
- `POST /api/chat/stream` emits content events, one metadata event containing citations and trace data, then `[DONE]`.
- The React application consumes this POST-based SSE stream through `fetch`, not browser `EventSource`, because the request includes a JSON body.

## Evidence Boundaries

The following are targets, not current architecture results:

- Qwen3-32B BF16 serving.
- 150+ deduplicated department courses.
- 92% retrieval or answer relevance.
- 65–70% GPU compute utilization.
- Resume-grade tokens/sec and error-rate measurements.

`--gpu-memory-utilization 0.85` is a vLLM memory reservation cap; it is not a measurement of GPU compute utilization. Each target requires the raw artifacts defined in the roadmap before its status or resume wording changes.

## Next Architecture Milestones

1. Reproduce real MiniLM ingestion and evaluate retrieval against a frozen advisor-style query set.
2. Add application metrics and correlate them with vLLM and GPU telemetry.
3. Persist benchmark manifests and raw per-request JSON/CSV before changing the serving model.
4. Verify the current Docker WIP through a clean Compose smoke test.
5. Add Kubernetes manifests and recovery tests only after container reproducibility and a real cluster namespace are available.
