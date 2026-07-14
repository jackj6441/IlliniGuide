# LLM Serving Design

Status: Partial — the self-hosted vLLM and end-to-end streaming paths are implemented; application observability and resume-grade throughput/GPU/error evidence are not complete.

This document tracks the LLM serving layer of IlliniGuide Serve — the abstraction that lets the rest of the codebase call an LLM without knowing which backend is behind it, and the vLLM concepts every implementer needs to reason about the system.

## 1. Design Rule

Per `AGENTS.md` §16.2, every LLM call must go through a unified client. Route handlers, tools, and services never construct provider SDK clients themselves. This is what lets us swap `mock` ↔ `vllm_remote` ↔ `external_debug` with a one-line env change.

## 2. Backend Modes

Three modes, chosen via `LLM_BACKEND` env var. Order in the roadmap reflects the intended learning path.

| Backend | Status | Purpose |
|---|---|---|
| `mock` | Implemented (Task C1) | Deterministic, in-process backend. No network. Used for tests and local development before vLLM is available. |
| `vllm_remote` | Implemented (Tasks C3–C6) | OpenAI-compatible HTTP/SSE client against a self-hosted vLLM server. This is the primary serving path. |
| `external_debug` | Implemented adapter; debug only | Reuses the OpenAI-compatible client against an explicitly configured public provider. It is never used to claim self-hosted serving. |

## 3. Interface Contract

Public surface (see `backend/app/services/llm/`):

```python
from app.services.llm import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    MockLLMClient,
    create_llm_client,
)
```

- `LLMMessage(role, content)` — `role` must be `"system" | "user" | "assistant"`, content must be `str`.
- `LLMResponse(content, model, backend, latency_ms, prompt_tokens, completion_tokens)` — `latency_ms` is measured client-side; token counts may be `None` for backends that do not report them.
- `LLMClient` — a `Protocol` (structural typing). Implementations expose `generate(...)` for blocking responses and `stream_generate(...)` for asynchronous content deltas.
- `create_llm_client(backend=None, model_name=None)` — factory reading `LLM_BACKEND` / `MODEL_NAME`, falling back to `mock` / `mock-model`. It builds real `vllm_remote` and `external_debug` clients when their required base URL is configured, and raises `ValueError` for missing configuration or an unknown backend.

## 4. vLLM Concepts (foundational, must know before Task C3)

The Phase C implementation is only useful if the implementer can reason about why vLLM is worth self-hosting. Five concepts.

### 4.1 Prefill vs decode

A single inference has two phases with different performance profiles.

- **Prefill**: process every prompt token in one parallel forward pass, populate KV cache. Compute-bound. Fully parallel. GPU utilization high.
- **Decode**: autoregressive, one new token per step. Each step reads all model weights and all KV cache entries. Memory-bandwidth-bound. GPU compute utilization low.

Almost every LLM serving optimization exists to increase GPU utilization during decode.

### 4.2 Memory arithmetic (worked example)

24 GB GPU, Llama-2-7B, fp16:

```
Weights   = 7B × 2 bytes         = 14 GB
Activations reserve              ≈  2 GB
Available for KV cache           =  8 GB
```

KV cache per token (Llama-2-7B, fp16):

```
per_token = 2 × num_layers × num_kv_heads × head_dim × dtype_bytes
          = 2 × 32         × 32           × 128      × 2
          ≈ 512 KB
```

Concurrency ceiling:

```
Total tokens across all in-flight requests = 8 GB / 512 KB ≈ 16 K
Assuming ~1000 tokens per request (prompt + generation)
=> ~16 concurrent users on 24 GB.
```

Same math on H100 80 GB:

```
80 - 14 - 5 = 61 GB for KV cache → 61 GB / 512 KB ≈ 125 K tokens
=> ~125 concurrent users at 1000 tokens each.
```

**Interview line:** "concurrency is not a network question; it is bounded by KV cache capacity, which is `(VRAM - weights - activations) / (per-token KV size)`."

### 4.3 Continuous batching

Traditional static batching waits for N requests, runs them together, and cannot start the next batch until every request in the current batch finishes. Short requests wait for long ones; batch boundaries idle the GPU.

Continuous batching schedules at the decode-iteration granularity: at every generation step the scheduler removes finished requests and admits queued ones into available slots. This reduces decode-batch idleness and amortizes weight reads across requests. It does not eliminate every queueing effect: a near-simultaneous cold burst can still experience prefill contention, which is visible in the measured p95 TTFT below.

### 4.4 PagedAttention

Fragmentation of the KV cache is the reason contiguous allocation caps concurrency. vLLM's PagedAttention borrows OS virtual-memory paging: split KV cache into fixed-size pages (e.g., 16 tokens), allocate pages on demand, let pages from different requests interleave physically, and index them per request through a block table. The attention kernel itself is rewritten to read K/V through this indirection, so no copy step is needed.

Effect: 2–4× more concurrent requests in the same VRAM.

### 4.5 TTFT vs total latency vs tokens/sec

Three latency metrics that must be reported separately.

- **TTFT** (time to first token): dominated by prefill. Streaming makes TTFT ≪ total latency because the user sees output immediately after prefill instead of waiting for full generation.
- **TPOT / ITL** (time per output token): dominated by decode step latency. Falls slowly as batch size grows.
- **Total latency**: `TTFT + n_output * TPOT`. This is what non-streaming callers care about.
- **Tokens/sec (server-side)**: throughput. Unaffected by streaming — streaming is purely a client-facing UX win.

Benchmarks must report p50/p95/p99 for at least TTFT and total latency; a single average hides the tail behavior that matters for user experience.

## 5. Implementation State

### Task C1 — LLMClient abstraction + Mock backend

Status: Implemented

- `services/llm/schemas.py` defines the message and response contracts with validation.
- `services/llm/client.py` implements `MockLLMClient` and the factory. Mock returns a deterministic string echoing the last user message, with real `latency_ms` measurement and estimated token counts so downstream metrics do not have to special-case `None`.
- Env vars: `LLM_BACKEND`, `MODEL_NAME` (already listed in `.env.example`).
- Tests in `backend/tests/test_llm_client.py` cover happy paths, validation, streaming, factory defaults, environment resolution, explicit-argument precedence, and missing/unknown backend configuration.

### Task C2 — Wire answer_synthesis to LLMClient

Status: Implemented

- `services/llm/prompt_templates.py` — per-intent system prompts and user-prompt builders. System prompts encode behavior constraints (grounding, evidence-only, no numeric scores in recommendation).
- `services/answer_synthesis.build_answer` is now async, takes an `LLMClient` and `ToolTraceCollector`, calls `client.generate(messages)`, and returns the LLM response content.
- `advising_service.build_chat_response` is now async, receives an optional `llm_client` (injectable for tests) and calls the factory otherwise. `api/chat.py` awaits it.
- The LLM call is recorded in the trace as a `llm_generate` tool with backend / model / n_messages arguments and prompt / completion token counts in the result summary. `used_tools` now includes `llm_generate` as its last entry.
- **Fallback:** any exception from `llm_client.generate` is recorded as `status="error"` in the trace, then `build_answer` returns the deterministic template branch that used to be the only path. A note is added to the collector explaining the fallback, so debug consumers see both what failed and how the answer was recovered.
- Tests: `test_prompt_templates.py` (10 tests) unit-test per-intent prompt shape; `test_answer_synthesis.py` (6 tests) inject a recording client and a failing client to prove success and fallback paths; `test_api.py` was updated for the new `used_tools` shape and added a check that LLM backend metadata is captured in the trace.

### Task C3 — VLLMRemoteBackend

Status: Implemented

- `services/llm/vllm_backend.py` — `VLLMRemoteClient` is a `dataclass` that speaks OpenAI-compatible `POST /v1/chat/completions` via `httpx.AsyncClient`. One class covers both `vllm_remote` and `external_debug` backends; only the `backend_name` and env resolution differ.
- **Retry policy**: exponential backoff (default 0.5 → 1.0 → 2.0 seconds) with `max_retries=2` (3 total attempts). Retries only on `httpx.ConnectError` / `ConnectTimeout` / `ReadTimeout` / `RemoteProtocolError` / HTTP 5xx. HTTP 4xx raises `VLLMClientError` immediately — retrying a bad request just wastes budget.
- **Auth**: `Authorization: Bearer {api_key}` added only when `api_key` is set; local vLLM without auth works out of the box.
- **Errors**: `VLLMBackendError` base, `VLLMServerError` (retriable / final), `VLLMClientError` (never retried). All propagate to `answer_synthesis` where the Task C2 graceful-degradation path records them and falls back to the template answer.
- **Env resolution** (in `client.create_llm_client`):
  - `vllm_remote`: requires `VLLM_BASE_URL`; optional `VLLM_API_KEY`, `MODEL_NAME`.
  - `external_debug`: prefers `EXTERNAL_LLM_BASE_URL` / `EXTERNAL_LLM_API_KEY`, falls back to `VLLM_*` if unset. Never used to claim self-hosted serving.
- **Testing**: 11 unit tests in `test_vllm_backend.py` use `httpx.MockTransport` to assert payload shape, headers, retry behavior, 4xx short-circuit, and response parsing — zero network dependency. 5 new factory tests in `test_llm_client.py` cover env resolution and error paths.
- **Deferred optimization**: connection-pool reuse (currently one `AsyncClient` per call — small overhead, correctness-first).

### Task C4 — Launch vLLM on ICRN H200 + smoke test

Status: Implemented

First real self-hosted inference measurements (Qwen2.5-7B-Instruct on ICRN H200, cold-cache, single-request):

- LLM call latency (wall): 231 ms
- Prompt tokens: 99, completion tokens: 18
- Average TTFT over first 2 requests: 506 ms
- `debug_trace.tool_calls[-1].arguments.backend == "vllm_remote"` — confirmed the request path is fully self-hosted, no external API.

Notes and gotchas discovered during the first ICRN run (folded back into `docs/vllm_setup.md` troubleshooting):

- Default `pip install vllm` pulled a version compiled against CUDA 13; ICRN driver caps at CUDA 12.8. Fix: pin `vllm<0.20` so pip picks a wheel linked against a CUDA 12.x runtime that the driver can load.
- `pip install torch` alone can pull a wheel built for a CUDA newer than the driver supports. Fix: install PyTorch with the CUDA-specific index (`--index-url https://download.pytorch.org/whl/cu128`) matching the driver's CUDA capability.
- A few Prometheus metric names differ across vLLM versions; the snapshot script tolerates missing metrics rather than crashing.
- Postgres is not running on ICRN by default. On the first end-to-end test, `get_course_profile` and `search_course_docs` failed with `psycopg.OperationalError`. The dispatcher's per-tool error isolation held: the request did not 500; the LLM was invoked with empty evidence; the grounding constraint in the system prompt made the model respond honestly with "insufficient information" instead of hallucinating. Wiring Postgres on ICRN (or switching to a local SQLite-shaped alternative for demo) is a separate task, not a C4 blocker.

Target machine: **ICRN H200** (141 GB VRAM, free to UIUC students via https://jupyter.ncsa.illinois.edu/). Full step-by-step manual lives in `docs/vllm_setup.md`.

Verified baseline model: **`Qwen/Qwen2.5-7B-Instruct`**, FP16, no quantization, tensor parallel size 1 (vLLM default; no `--tensor-parallel-size` override), 8192-token maximum model length, and prefix caching enabled. Its weights are roughly 14 GB; `--gpu-memory-utilization 0.85` gives vLLM a roughly 120 GB total weights-and-cache budget on a 141 GB H200 allocation, not 120 GB of KV cache alone.

Launch flags and their rationale are documented in `docs/vllm_setup.md` step 4. Key ones:

- `--dtype float16` — half precision, 2 bytes/param
- `--max-model-len 8192` — bounds max KV cache per request
- `--gpu-memory-utilization 0.85` — vLLM plans weights and its cache pool within 85% of VRAM; this is a memory-budget cap, not measured GPU compute utilization
- `--enable-prefix-caching` — critical for our workload because every request shares the same system prompt

Two helper scripts land with this task:

- `scripts/verify_vllm.py` — sends one chat completion through the `vllm_remote` backend and reports latency + tokens. Fast go/no-go check after `vllm serve` boots.
- `scripts/vllm_metrics_snapshot.py` — parses vLLM's `/metrics` (Prometheus text format) and prints only the metrics that matter for the concepts in section 4 of this doc: KV cache %, queued vs running requests, prompt/decode token counters, average TTFT. Pedagogical — helps validate that KV cache usage and TTFT behave the way section 4 says they should under load.

The original completion gate was satisfied by a real `/api/chat` response whose final trace entry reported `backend == "vllm_remote"`, together with the smoke measurements above. Future environment rebuilds should repeat the same verification rather than assuming a launch script alone proves serving works.

### Task C5 — Streaming (SSE) end-to-end

Status: Implemented

This capability is implemented end to end in the backend and frontend.

- **Protocol**: `LLMClient` now declares both `generate` (blocking) and `stream_generate` (async iterator of content deltas). Old callers are unaffected; streaming is a new capability, not a rewrite.
- **MockLLMClient.stream_generate**: yields the deterministic mock output in ~6-character chunks with a small `asyncio.sleep` between them so tests can exercise real async iteration timing.
- **VLLMRemoteClient.stream_generate**: sends `stream: true` in the OpenAI payload, opens a streaming HTTP response with `httpx.AsyncClient.stream("POST", ...)`, iterates SSE `data:` lines, JSON-decodes each, and yields `choices[0].delta.content`. Role-only preamble lines, `[DONE]`, and malformed JSON lines are tolerated (never surface as content). Retries are intentionally not applied to streams — retrying mid-stream would either duplicate content or lose position; failures propagate.
- **answer_synthesis.stream_answer**: async generator wrapping `client.stream_generate`. Three paths, all recorded in the trace as `llm_generate_stream`:
  - happy: yields chunks, records `status=success` with `chunks_yielded`.
  - fails before first chunk: records `status=error`, adds a note, yields the deterministic template answer as a single chunk (graceful degradation preserved).
  - fails mid-stream: records `status=error` with `partial: True`, adds a truncation note. Already-yielded chunks stay — the user sees a truncated but honest answer, not a discarded one.
- **`ToolTraceCollector.record_completed_tool`**: new public method that records a `ToolCallTrace` given caller-measured latency and status. Used by streaming, where the sync `time_tool` context manager can't cleanly wrap an async generator's yield loop.
- **New endpoint** `POST /api/chat/stream` returns `StreamingResponse(..., media_type="text/event-stream")`. Sends `Cache-Control: no-cache` and `X-Accel-Buffering: no` so intermediaries (nginx, ICRN's JupyterHub proxy) do not buffer chunks. The existing `POST /api/chat` (blocking) remains untouched — clients pick per request.
- **Event schema** (line-delimited, SSE-standard `\n\n` terminator):

```
data: {"type": "content", "delta": "<chunk>"}
data: {"type": "content", "delta": "<chunk>"}
...
data: {"type": "metadata", "citations": [...], "used_tools": [...], "latency_ms": 523, "debug_trace": {...}?}
data: [DONE]
```

`citations`, `used_tools`, and `latency_ms` are always present in the `metadata` event. `debug_trace` appears only when the request body has `debug: true`.

- **Tests**: targeted cases cover mock stream chunking and validation, SSE parsing and HTTP failures, fail-before-first-chunk fallback, mid-stream truncation, end-to-end endpoint framing, and debug-trace gating.

The React frontend consumes this stream with a `fetch`-based SSE parser, renders deltas progressively, and supports cancellation. `fetch` is used because this is a `POST` request with a JSON body; the browser `EventSource` API only supports `GET`.

### Task C6 — Benchmark harness + historical latency notes

Status: Partial

The harness and the latency notes below are implemented. The overall task remains Partial because there is no immutable raw JSON/CSV run artifact, manifest, saved error-rate result, or same-window GPU telemetry.

Measured on an ICRN H200 allocation with Qwen2.5-7B-Instruct, concurrency 10, 47 counted requests, `backend/scripts/benchmark.py`:

- **Streaming p50 TTFT: 55 ms** (single-user warm-cache floor: 23 ms)
- **Blocking p50 full-response latency: 472 ms**. A blocking JSON response reveals no token before completion, so this is time to first visible response rather than server-side TTFT.
- **Client-visible response onset: about 8.6× earlier with streaming at p50** (55 ms first streamed content versus 472 ms complete blocking response). This does not mean streaming accelerated model generation.
- Streaming p50 total latency: 477 ms
- Streaming p95 TTFT: 4456 ms; streaming p95 total latency: 5051 ms
- Blocking p95 full-response latency: 701 ms

The streaming p95 is preserved as a **cold-burst tail**, not relabeled as steady-state performance. The first near-simultaneous cohort waited through prefill contention; later requests clustered near the much lower median. A future warm steady-state run must use an explicit warmup window and publish its own p95 rather than replacing or hiding this result.

The historical command shape that produced 47 counted requests from 50 total requests was:

```bash
cd backend
python -m scripts.benchmark --endpoint stream --concurrency 10 --total-requests 50
python -m scripts.benchmark --endpoint chat --concurrency 10 --total-requests 50
```

These commands make the workload shape explicit, but they are not a substitute for the missing raw per-request artifact and environment manifest. The values above are therefore retained as historical notes rather than promoted to a resume-grade benchmark package.

In the current harness, `--warmup 3` means the first three scheduled request indices are excluded from aggregation. They are launched through the same semaphore/gather run as counted traffic; this is **not** a separate pre-run warmup phase and must not be described as a warm steady-state measurement.

Interview notes in `docs/interview_notes_vllm.md` include the resume bullet, a 60-second pitch, 16 L1/L2/L3 questions grounded in these measurements (including the burst-behavior walkthrough), explicit tradeoffs, and failure modes.

- `backend/scripts/benchmark.py` — self-contained concurrent load test built on `httpx.AsyncClient`. It can calculate client-observed TTFT, total latency, approximate output throughput, and error rate for blocking and streaming paths.
- `docs/interview_notes_vllm.md` — records the measured latency distributions and explains the cold-burst tail.

The existing saved notes establish the latency numbers above, but do **not** preserve defensible resume values for aggregate tokens/sec, error rate, or GPU compute utilization. The current throughput calculation is approximate, and the run was not saved as structured JSON/CSV with a manifest. These remain Partial rather than inferred from the script's capability.

### Task C7 — Observability and resume-grade evidence

Status: Partial

- Implemented: a pedagogical vLLM `/metrics` snapshot helper for selected server counters.
- Partial: application Prometheus metrics now cover request/error counts, HTTP
  and tool latency/status, and streaming TTFT. Missing: retrieval/LLM-specific
  latency histograms, Prometheus scraping, and Grafana.
- Missing: Prometheus scrape configuration and a verified Grafana dashboard.
- Missing: same-window GPU compute utilization sampling, VRAM usage, KV-cache utilization, queue depth, structured benchmark output, and a counted-request error denominator.

`--gpu-memory-utilization 0.85` must never be reported as “85% GPU utilization.” Resume claims such as “65–70% GPU utilization” require timestamped compute-utilization samples from the same named load run.

### Future Target — Qwen3-32B BF16

Status: Planned

Qwen3-32B BF16 is a planned model-migration experiment. It becomes a project fact only after the repository preserves the exact launch command, startup log, `/v1/models` response, smoke output, reasoning/non-thinking response compatibility check, and a model-specific benchmark artifact. Until that gate passes, all current serving and resume descriptions must use the verified Qwen2.5-7B-Instruct FP16 baseline.

## 6. Non-Goals

- Building a training pipeline. This is a serving project.
- Reimplementing tokenizers. vLLM handles tokenization internally; the client only sees strings.
- Automated model selection. Model choice is a manual per-deployment decision documented in `docs/vllm_setup.md`.
- Multi-provider load balancing. If needed later, it lives outside `services/llm/` — the client stays single-backend.
