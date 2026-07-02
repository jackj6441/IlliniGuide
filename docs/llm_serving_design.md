# LLM Serving Design

Status: Partial

This document tracks the LLM serving layer of IlliniGuide Serve — the abstraction that lets the rest of the codebase call an LLM without knowing which backend is behind it, and the vLLM concepts every implementer needs to reason about the system.

## 1. Design Rule

Per `AGENTS.md` §16.2, every LLM call must go through a unified client. Route handlers, tools, and services never construct provider SDK clients themselves. This is what lets us swap `mock` ↔ `vllm_remote` ↔ `external_debug` with a one-line env change.

## 2. Backend Modes

Three modes, chosen via `LLM_BACKEND` env var. Order in the roadmap reflects the intended learning path.

| Backend | Status | Purpose |
|---|---|---|
| `mock` | Implemented (Task C1) | Deterministic, in-process backend. No network. Used for tests and local development before vLLM is available. |
| `vllm_remote` | Planned (Task C3) | OpenAI-compatible HTTP client against a self-hosted vLLM server. This is the production path. |
| `external_debug` | Planned (Task C3) | OpenAI-compatible HTTP client against a public provider (e.g., OpenAI). Development-only fallback so we can compare quality when vLLM is not reachable. Never used to claim "self-hosted" in docs or resume bullets. |

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
- `LLMClient` — a `Protocol` (structural typing). Any type with `backend_name`, `model_name`, and `async def generate(messages, *, temperature, max_tokens)` is a valid client.
- `create_llm_client(backend=None, model_name=None)` — factory reading `LLM_BACKEND` / `MODEL_NAME` env vars, falling back to `mock` / `mock-model`. Raises `NotImplementedError` for backends whose implementation has not landed yet, `ValueError` for unknown backends.

Streaming (`stream_generate`) is deliberately deferred to Task C5 so C1–C3 stay small and testable.

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

Continuous batching schedules at the decode-iteration granularity: at every generation step the scheduler evicts finished requests and admits queued ones into empty slots. Result: the GPU's batch is always full and there is no head-of-line blocking. Throughput grows sub-linearly with batch size because decode is memory-bandwidth-bound and larger batches amortize the weight-read cost across more tokens.

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
- Tests: `backend/tests/test_llm_client.py` (17 tests) cover happy path, custom model, invalid role/content/temperature/max_tokens, factory defaults, env resolution, explicit-argument precedence, unknown-backend error, and `NotImplementedError` shape for the vllm_remote / external_debug placeholders.

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
- **Deferred**: streaming (Task C5), connection-pool reuse (currently one AsyncClient per call — small overhead, correctness-first).

### Task C4 — Launch vLLM on ICRN H200 + smoke test

Status: Manual — awaiting execution

Target machine: **ICRN H200** (141 GB VRAM, free to UIUC students via https://jupyter.ncsa.illinois.edu/). Full step-by-step manual lives in `docs/vllm_setup.md`.

Chosen model: **Qwen2.5-7B-Instruct** (fp16, 14 GB weights, ~120 GB left for KV cache — vastly more concurrency than we need for demo/eval). Not gated on HuggingFace, so no token is needed.

Launch flags and their rationale are documented in `docs/vllm_setup.md` step 4. Key ones:

- `--dtype float16` — half precision, 2 bytes/param
- `--max-model-len 8192` — bounds max KV cache per request
- `--gpu-memory-utilization 0.85` — vLLM claims 85% of 141 GB for weights + KV cache pool
- `--enable-prefix-caching` — critical for our workload because every request shares the same system prompt

Two helper scripts land with this task:

- `scripts/verify_vllm.py` — sends one chat completion through the `vllm_remote` backend and reports latency + tokens. Fast go/no-go check after `vllm serve` boots.
- `scripts/vllm_metrics_snapshot.py` — parses vLLM's `/metrics` (Prometheus text format) and prints only the metrics that matter for the concepts in section 4 of this doc: KV cache %, queued vs running requests, prompt/decode token counters, average TTFT. Pedagogical — helps validate that KV cache usage and TTFT behave the way section 4 says they should under load.

DoD: user runs the manual through Step 8, verifies `debug_trace.tool_calls[-1].arguments.backend == "vllm_remote"` in a real `/api/chat` response, and pastes the answer + metrics snapshot. At that point the status here flips to Implemented and README is updated with the actual measured TTFT.

### Task C5 — Streaming (SSE) end-to-end

Status: Planned

Extend `LLMClient` with `stream_generate` returning `AsyncIterator[str]`, add a streaming variant of `/api/chat`, wire a client using `EventSource`. Measure TTFT vs total latency and record the delta in the benchmark report.

### Task C6 — Benchmark + interview notes

Status: Planned

Run a 10-concurrency load test on the H100 vLLM deployment; record TTFT / p95 total latency / tokens_per_sec. Publish `docs/interview_notes_vllm.md` with L1/L2/L3 Q&A per `AGENTS.md` §22.

## 6. Non-Goals

- Building a training pipeline. This is a serving project.
- Reimplementing tokenizers. vLLM handles tokenization internally; the client only sees strings.
- Automated model selection. Model choice is a manual per-deployment decision documented in `docs/vllm_setup.md`.
- Multi-provider load balancing. If needed later, it lives outside `services/llm/` — the client stays single-backend.
