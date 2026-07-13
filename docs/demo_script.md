# Demo Script

Status: Partial

The core AI-serving prototype is demonstrable: React UI, FastAPI service orchestration, structured academic tools, citation-oriented retrieval, self-hosted Qwen2.5-7B-Instruct through vLLM, and SSE streaming are implemented. The demo must still describe semantic retrieval quality, observability, Docker, and Kubernetes according to their actual status below.

For remaining evidence gates, see [todo_roadmap.md](todo_roadmap.md). For the coordinated delivery sequence, see [multi_agent_delivery_plan.md](multi_agent_delivery_plan.md).

## Before the Demo

1. Start PostgreSQL, vLLM, and the backend on ICRN:

   ```bash
   bash scripts/dev_up.sh
   ```

2. Confirm `GET /health` and the vLLM model endpoint respond.
3. Confirm the backend is configured with `LLM_BACKEND=vllm_remote` and the verified Qwen2.5-7B-Instruct model, not the local mock backend.
4. Start the React frontend and open the chat page.
5. Use `debug=true` for at least one request so the tool plan, tool latency, and serving backend can be shown.

If the live H200 endpoint is unavailable, switch to the deterministic mock backend and say so explicitly. Do not present that fallback run as self-hosted inference evidence.

## Demonstrable Flow

### 1. Course question with streaming and citations

Prompt:

> What is ECE 391 about, and what should I know before taking it?

Show:

- The answer appears incrementally through `POST /api/chat/stream`.
- The frontend remains cancellable while generation is in progress.
- The response includes course evidence/citations and structured prerequisite facts.
- Debug trace shows the selected intent and ordered tool/LLM records. The documented architecture explains that the thin route delegates to the advising service, router, and dispatcher; those orchestration stages are not separate trace events.

Explain:

> “The LLM explains retrieved evidence, but prerequisites and other reliable course facts come from structured tools. This reduces unsupported generation and keeps each component independently testable.”

### 2. Structured comparison

Prompt or UI action:

> Compare ECE 408 and ECE 391.

Show:

- Both course profiles are loaded through deterministic tool logic.
- GPA, prerequisite readiness, and direction tags remain structured fields.
- The explanation layer presents the comparison without inventing unavailable values.

### 3. Recommendation

Prompt or UI action:

> Recommend systems or machine-learning courses after ECE 220.

Show:

- Recommendations use direction match, prerequisite readiness, GPA risk, and progression signals.
- Debug mode can expose the score breakdown, while the normal UI presents a natural explanation.

### 4. Self-hosted serving and failure behavior

Show:

- The configured model is the verified Qwen2.5-7B-Instruct FP16 baseline served by vLLM on ICRN H200.
- `debug_trace` identifies the `vllm_remote` backend.
- A generation failure before the first chunk falls back to a deterministic answer; a mid-stream failure preserves emitted text and reports truncation instead of silently restarting.

Explain:

> “vLLM provides an OpenAI-compatible server while keeping inference self-hosted. Its continuous batching and KV-cache management improve serving efficiency; the FastAPI application remains provider-independent through a unified client abstraction.”

### 5. Saved benchmark evidence

State only the measurements currently supported by saved notes:

- Model: Qwen2.5-7B-Instruct on ICRN H200.
- Load: concurrency 10, 47 counted requests per run.
- Streaming p50 client-observed TTFT: 55 ms.
- Blocking p50 full-response latency: 472 ms. Because the blocking JSON endpoint exposes output only after completion, this is the time to first visible response, not a measured server-side TTFT.
- Streaming cold-burst p95 TTFT: 4.456 s; keep this visible because it shows queueing in the initial cohort.

Explain that streaming improves perceived latency but does not by itself improve total generation throughput. Do not quote tokens/sec, error rate, or GPU compute utilization because those results were not saved.

## Status Boundaries During the Demo

| Capability | Status | What may be shown or claimed |
|---|---|---|
| React frontend + SSE | Implemented | Incremental rendering, cancellation, citations, comparison, and recommendation UI. |
| Tool orchestration | Implemented | Router, dispatcher, structured tools, answer synthesis, and debug trace. |
| Self-hosted vLLM | Implemented | Qwen2.5-7B-Instruct FP16 baseline on ICRN H200. |
| Semantic pgvector RAG | Partial | Implemented code path may be demonstrated, but no quality percentage is valid until a live labeled evaluation is saved. |
| Benchmark | Partial | Use the historical TTFT/latency figures above together with the command and limitations in `llm_serving_design.md`; tokens/sec, error rate, and GPU utilization remain unmeasured in saved artifacts. |
| Observability | Partial | Per-tool trace and manual vLLM metrics snapshot only; no completed Prometheus/Grafana story yet. |
| Docker | Partial | Image files are WIP, but do not describe Compose as verified. |
| Kubernetes | Planned | Describe only as a future reliability phase. |

## Claims That Are Still Targets

Do not present these as completed during the demo:

- Qwen3-32B BF16 serving.
- 150+ indexed department courses; the current evidenced baseline is 80 ECE courses.
- 92% relevance.
- 65–70% GPU compute utilization.
- Production-ready Docker or Kubernetes deployment.

Each claim becomes usable only after the roadmap's raw-artifact gate is satisfied.

## 60-Second Demo Narrative

> “IlliniGuide Serve is a self-hosted academic-advising prototype, not just a chat UI. A React client sends blocking or streaming requests to thin FastAPI routes. The advising service plans structured tools, executes them with isolated failure handling, retrieves cited course evidence, and sends that context through a unified LLM client to Qwen2.5-7B-Instruct served by vLLM on an ICRN H200. I benchmarked the streaming path at concurrency 10 and recorded a 55 ms median client-observed TTFT, while also preserving the 4.456-second cold-burst p95 tail. The next milestones are a labeled RAG evaluation, application and GPU telemetry, clean Compose verification, and then Kubernetes recovery testing.”
