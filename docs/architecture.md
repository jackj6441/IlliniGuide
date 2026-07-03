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
- Bounded WAF GPA CSV ingestion into `courses` and `gpa_stats`.
- Bounded ECE prerequisite ingestion into `courses`.
- Manual career tag seed for selected core courses already present in `courses`.
- DB-aware mock RAG service with course ID normalization, keyword retrieval, citation formatting, and sample chunk fallback.
- First structured course tool: `get_course_profile`.
- Structured GPA stats tool: `get_gpa_stats`.
- Structured prerequisite check tool: `check_prerequisites`.
- Structured course comparison tool: `compare_courses`.
- Structured course recommendation tool: `recommend_courses`.
- Structured document search tool: `search_course_docs` (explicit-schema wrapper over the DB-aware retriever, with course-ID normalization and empty/fallback notes).
- Manual tool router (rule-based intent detection producing a `ToolPlan`; four intents; priority-ordered with safe downgrades and empty-signal notes).
- `ToolTraceCollector` in `services/tools/trace.py` — context-manager timing of every tool call, with status/error/latency/result-summary; serialized to `DebugTrace` only when `debug=true`.
- Tool dispatcher in `services/tools/dispatcher.py` — executes a `ToolPlan` against real tool functions, isolates per-tool errors so one failing tool does not abort the request, and records `chunks`/`recommendation_scores` into the collector.
- `services/answer_synthesis.py` — intent-specific template answer builder over `DispatchedResults`. Every branch ends with an explicit `TODO: replace with LLM synthesis after vLLM integration` marker.
- `/api/chat` is now a real three-stage pipeline: `plan_tools` → `execute_plan` → `build_answer`. LLM synthesis is still template-based; `/api/compare` and `/api/recommend` remain mocked and will be wired in a later task.
- LLM client abstraction (`services/llm/`): `LLMMessage` / `LLMResponse` schemas, `LLMClient` Protocol, `MockLLMClient`, and a `create_llm_client()` factory reading `LLM_BACKEND` / `MODEL_NAME` env vars. See `docs/llm_serving_design.md` for vLLM concepts and Phase C roadmap.
- `services/llm/prompt_templates.py`: per-intent system prompts and user-prompt builders that serialize `DispatchedResults` into evidence blocks.
- `services/answer_synthesis.build_answer` is now async: it calls the injected `LLMClient` and, on failure, records `status="error"` in the trace and returns a deterministic template answer (graceful degradation). `advising_service.build_chat_response` is async and constructs the LLM client via the factory when the caller does not inject one.
- `services/llm/vllm_backend.py`: `VLLMRemoteClient` — OpenAI-compatible HTTP client (`httpx.AsyncClient` over `/v1/chat/completions`) with exponential-backoff retry (network + 5xx only) and typed errors (`VLLMServerError` retriable, `VLLMClientError` never retried). One class serves both `vllm_remote` and `external_debug` backends; the factory resolves env differently for each.
- Self-hosted vLLM running on ICRN H200 with `Qwen2.5-7B-Instruct`. First smoke test measured 231 ms LLM call latency and 506 ms avg TTFT. See `docs/vllm_setup.md` for launch details; `scripts/verify_vllm.py` and `scripts/vllm_metrics_snapshot.py` are one-command diagnostics.
- `LLMClient` extended with `stream_generate` returning an `AsyncIterator[str]` of content chunks. `MockLLMClient` yields the mock content in ~6-char slices with a small `asyncio.sleep`; `VLLMRemoteClient` opens a streaming `POST /v1/chat/completions` with `stream: true` and parses OpenAI-style SSE `data:` lines. Retries are not applied to streams — retry semantics do not compose with mid-stream state.
- `services/answer_synthesis.stream_answer` async generator wraps the streaming call, records `llm_generate_stream` in the collector on completion (success or error), and falls back to a one-shot template answer only when the LLM fails **before** any chunk reached the client. Mid-stream errors are recorded with `partial: True` and a truncation note; already-yielded chunks are preserved.
- New endpoint `POST /api/chat/stream` returns `StreamingResponse(media_type="text/event-stream")`. Content chunks arrive as `data: {"type": "content", "delta": ...}` events; a single `data: {"type": "metadata", ...}` event carries citations, `used_tools`, `latency_ms`, and (when `debug=true`) `debug_trace`; the stream ends with `data: [DONE]`.
- `backend/scripts/benchmark.py` — async load test that fires N concurrent requests against either `/api/chat` or `/api/chat/stream`, records per-request TTFT (streaming only) and total latency, and reports p50/p95/p99. Prompts cycle across four advising templates so prefix caching doesn't inflate TTFT results. Feeds the numbers in `docs/interview_notes_vllm.md`.

## Planned

- Service-layer RAG and tool orchestration.
- Alembic migrations.
- Real PostgreSQL connection tests.
- React frontend for chat and course comparison.
- vLLM-compatible LLM client abstraction.
- Prometheus/Grafana observability.
- Evaluation and benchmark reports.

## Current Boundary

The current API behavior is still mocked. It validates request/response shapes and route structure. Some database-backed services and structured tools now exist, but API-level tool routing, embedding retrieval, and vLLM calls are not wired in yet.

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
