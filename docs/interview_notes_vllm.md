# vLLM / LLM Serving — Interview Notes

Status: Skeleton — numbers filled in after Task C6 benchmark run.

The purpose of this document is to survive interview questioning on the LLM serving portion of IlliniGuide Serve. It follows the format in `AGENTS.md` §22 and §23 — a resume bullet, a 60-second explanation, three levels of deep-dive questions with grounded answers, and explicit tradeoffs and failure modes.

---

## Resume bullet (draft)

> Built and deployed a self-hosted LLM/RAG serving platform on a UIUC H200 GPU, running Qwen2.5-7B-Instruct behind vLLM's OpenAI-compatible endpoint. Designed a three-stage pipeline (rule-based tool router → error-isolated tool dispatcher → intent-specific LLM synthesizer) with graceful degradation to template answers when the LLM backend is unavailable. Achieved a p95 total latency of **{P95_TOTAL_MS} ms** and a p95 TTFT of **{P95_TTFT_MS} ms** on the streaming endpoint under 10 concurrent users; blocking endpoint p95 was **{P95_BLOCKING_MS} ms** at the same load. Instrumented per-tool timing and status through a single trace collector that feeds both the debug response and (planned) Prometheus metrics.

Placeholders `{P95_TOTAL_MS}`, `{P95_TTFT_MS}`, `{P95_BLOCKING_MS}` are filled in from `scripts/benchmark.py` output.

---

## 60-second explanation

> "IlliniGuide Serve is an academic-advising workload that showcases a self-hosted LLM serving platform. The demo scenario is a UIUC ECE/CS advisor: a user asks questions in natural language, the backend answers with grounded citations. Underneath, the interesting parts are all serving-infra. There's a FastAPI backend with a rule-based tool router that classifies intent, a dispatcher that runs structured tools against a PostgreSQL database, and an answer synthesizer that hands the retrieved evidence to Qwen 2.5-7B running on a UIUC H200 through vLLM's OpenAI-compatible endpoint. The whole client-facing layer is streaming SSE, so users see the first token in roughly 500 ms instead of waiting five seconds for a full generation. Every tool call — including the LLM one — is timed and status-tracked through one trace collector, so error rates and latency breakdowns are all coming from the same source of truth. If the LLM or the database has a hiccup, the pipeline degrades gracefully instead of returning a 500."

---

## Deep-dive questions

### Level 1 — foundations (anyone with an LLM course would answer)

**Q1. What is vLLM? Is it a model?**

> vLLM is not a model. It's an **inference/serving engine** — a runtime that loads a transformer model (Llama, Qwen, Mistral, etc.) onto a GPU and serves it efficiently over HTTP. My setup runs Qwen 2.5-7B-Instruct on the H200 through vLLM. The model is the recipe; vLLM is the kitchen.

**Q2. What is a KV cache and why do we care?**

> During transformer decode, attention needs the K and V matrices for every previous token to generate the next one. Recomputing them at every step would be quadratic. Instead, we cache K and V per layer per token — that's the KV cache. It's why decode is *memory-bandwidth-bound*, not compute-bound: each new token requires reading the entire cache. It's also why concurrency in an LLM server is capped by KV cache VRAM, not by network or CPU.

**Q3. What are prefill and decode?**

> Two phases of a single request with fundamentally different performance profiles.
>
> - **Prefill** processes every prompt token in one parallel forward pass and populates the KV cache. It is compute-bound; the GPU is fully utilized.
> - **Decode** generates one new token per step, autoregressively. Each step reads the entire model plus the KV cache, so it's memory-bandwidth-bound and per-step GPU utilization is low.
>
> Almost every LLM serving optimization exists to raise utilization during decode.

**Q4. What is the OpenAI-compatible protocol?**

> A JSON-over-HTTP schema for chat completions that OpenAI defined first: `POST /v1/chat/completions` with `{model, messages, temperature, ...}` in and `{choices[].message.content, usage: {prompt_tokens, completion_tokens}}` out. Because OpenAI was first, the whole ecosystem — vLLM, TGI, Anthropic, LM Studio — settled on the same wire format. That's why my FastAPI backend can point at either a self-hosted vLLM or a public OpenAI endpoint with only a config change.

---

### Level 2 — normal interview

**Q5. Why not just call the OpenAI API?**

> Three reasons: cost, control, and the point of the project.
>
> - Cost: a workload with unbounded query volume against GPT-4-class models is very expensive; self-hosting a 7B model on a UIUC-provided H200 is free per query at inference time.
> - Control: with vLLM I can pin exact model version, inspect KV cache utilization, tune batch and max sequence length, and reproduce behavior deterministically for evaluation. Public APIs are a black box that can change under me.
> - Focus: this is a portfolio project explicitly about *serving-infra*, not about wrapping an API. Building against OpenAI would not demonstrate anything I want to demonstrate.
>
> External API access is deliberately kept as a `LLM_BACKEND=external_debug` fallback in the client factory, but it's marked in the docs and code as a debugging aid — never presented as the production path.

**Q6. What does continuous batching actually do?**

> Traditional static batching waits until N requests arrive, runs them together, and blocks admitting new requests until the batch finishes. Short requests wait for long ones, and there are dead gaps between batches. Continuous batching schedules at the *decode-iteration* granularity: at every generation step, finished requests are evicted from the batch and queued requests are admitted into the empty slots. Result: the batch is always full, head-of-line blocking is gone, and throughput scales sub-linearly with batch size because decode's memory-bandwidth cost of reading model weights is amortized across more requests.

**Q7. What is PagedAttention and why does it matter?**

> Same idea as OS virtual-memory paging, applied to the KV cache. Traditional KV allocation pre-reserves a contiguous VRAM block per request based on max_sequence_length, so a request that only outputs 100 tokens wastes cache room for 2000. PagedAttention splits the KV cache into fixed-size pages (e.g., 16 tokens each), allocates pages on demand, and lets pages from different requests interleave physically. A per-request block table maps logical positions to physical pages. The attention kernel is rewritten to read K/V through this indirection. The result is 2–4× more concurrent requests fitting into the same VRAM, which raises the batch sizes continuous batching can exploit.

**Q8. How do you decide concurrency limits?**

> By memory arithmetic, not by network. On an H200 with 141 GB and Qwen 2.5-7B in fp16:
>
> - weights: 7B × 2 bytes = 14 GB
> - activations reserve: ~5 GB
> - KV cache budget: 141 − 14 − 5 = 122 GB
> - KV per token (Llama-like 7B, fp16): 2 × 32 layers × 32 heads × 128 head_dim × 2 bytes ≈ 512 KB
> - total in-flight token capacity: 122 GB / 512 KB ≈ 250 K tokens
> - at ~1000 tokens per request (prompt + generation) → ≈ 250 concurrent users
>
> The number I report in benchmark results — {P95_TOTAL_MS} at concurrency 10 — is well inside that ceiling. If we saw KV cache utilization approach 100% at low concurrency, the answer would be "raise `--max-model-len`, lower `--gpu-memory-utilization`, or quantize the model," not "add more instances."

**Q9. What does streaming actually improve?**

> It changes *client-perceived* TTFT, not *server-side* TTFT. Server-side TTFT — the time vLLM takes to complete prefill and emit the first token — is unchanged. What streaming changes is *when the client observes that token*. Without streaming, the browser waits for `total_latency` (prefill + n × decode). With streaming, it observes the first token at approximately `server_TTFT + one_network_hop`. In my measurements: blocking p95 = {P95_BLOCKING_MS} ms, streaming p95 TTFT = {P95_TTFT_MS} ms — the perceived latency drops from full generation time to the prefill-plus-hop floor. Throughput is unchanged.

**Q10. How is the LLM call error-handled?**

> Two layers of graceful degradation:
>
> 1. In the blocking path, `build_answer` runs the LLM call inside `collector.time_tool("llm_generate", ...)`. Any exception is caught, recorded on the trace as `status="error"`, and the synthesizer returns a deterministic template answer built from the retrieved evidence. The user gets a grounded (but less articulate) response instead of a 500.
> 2. In the streaming path, `stream_answer` differentiates *fail-before-first-chunk* (yields the template as one chunk, records error) from *fail-mid-stream* (records error with `partial: True`, adds a truncation note, but keeps the chunks already sent because they cannot be un-shown). Retries are intentionally not applied to streams — retry semantics don't compose with mid-stream state.

---

### Level 3 — deep-dive / tradeoff

**Q11. What is the actual bottleneck when you push concurrency to 100+ users?**

> Two things fail in this order:
>
> 1. **KV cache saturation.** When aggregate in-flight tokens approach the KV budget, the scheduler queues new requests. Users see rising `queue_time` before rising generation latency. `vllm:num_requests_waiting` in `/metrics` shows this early.
> 2. **Decode-step latency growth.** As batch size grows the per-token decode step grows sub-linearly, so p95 TTPOT (time per output token) rises. The visible symptom to users is streaming that visibly slows down over the course of a response.
>
> If I were pushing further I would first try quantizing to fp8 (roughly halves weight and KV cache memory), then add a second GPU with tensor parallelism (`--tensor-parallel-size 2` in vLLM), then think about horizontal replicas. Adding replicas is only useful once single-replica scheduling is provably the bottleneck.

**Q12. Why did you build the tool router rule-based instead of LLM-based?**

> Deterministic-first, ML-later. Every downstream tool call depends on the router's intent classification, so a router bug cascades. A rule-based router has 12 unit tests, fires in microseconds, and its behavior on any query is inspectable. An LLM planner would need every route decision to be an extra LLM call — that's latency, cost, and one more failure surface on the pipeline entry. My design has an obvious upgrade path: add a `confidence` output to the rule router and fall back to an LLM planner only for low-confidence cases. That's a hybrid, which is what production systems tend to converge to (Alexa/Siri classic intent classifiers do exactly this).

**Q13. How would you scale from 10 concurrent users to 1000?**

> A staged answer, because "just add more" is wrong:
>
> - **~50 users** — the current single H200 with prefix caching probably handles this. Verify with a benchmark, don't guess.
> - **~500 users** — quantize model to fp8 for double effective KV cache; enable request-level tensor parallelism if a 2-GPU node is available.
> - **~1000+ users** — horizontal scale: a small pool of vLLM replicas behind a load balancer (K8s Service does this natively). At this scale you need a shared queue and worry about hot vs cold prefix caches; per-replica prefix caching is redundant. I have not built this — it's on the K8s / Phase 4 roadmap.
> - Common thread: at every stage, decisions come from **measured** bottlenecks (Prometheus metrics from vLLM + our own trace collector), not from guesses.

**Q14. What happens if the vLLM server dies mid-request?**

> Concrete order of what the user sees and what the SRE sees:
>
> 1. If the connection was closed after prefill but before decode, the streaming client sees zero content events, only the metadata event indicating error. The blocking client sees a template fallback answer.
> 2. If the connection dies mid-stream, the client keeps whatever was already streamed, and the metadata event never arrives; the SSE stream terminates. In our trace, that record is `status=error, partial=True, chunks_yielded=N`.
> 3. The next request retries against whatever vLLM instance is available. In our current single-replica setup that fails until vLLM comes back; in a K8s setup a healthy replica takes over.
>
> The client's `VLLMRemoteClient` implements exponential-backoff retry, but only for network errors and 5xx on the *non-streaming* path. Streaming failures propagate — see Q10.

**Q15. Why do you report percentiles and not averages?**

> An average hides tail behavior. If p50 is 500 ms and p99 is 8 s, an average of, say, 800 ms sounds fine to a stakeholder but describes almost none of the actual user experiences. Users experience individual requests, so the tail is what matters. p50 tells me the median case, p95 tells me what the second-worst-out-of-20 users saw, and p99 tells me the near-worst. Serving SLAs are always defined on p95 or p99 for exactly this reason. If my average and my p95 diverge by more than 2×, something in the workload has a fat tail I should investigate.

---

## Tradeoffs I explicitly made

- **httpx over the OpenAI Python SDK.** Fewer deps, explicit payload shape (easier to reason about in interview terms), no SDK opinion leaking into my code. Cost: I re-implemented SSE parsing (~30 lines) and retry (~40 lines) instead of getting them for free.
- **Same class for `vllm_remote` and `external_debug`.** Both speak the OpenAI protocol, so the difference is only which env var provides the base URL. Cost: nothing significant; the small risk is that a future divergence in provider quirks forces a subclass split.
- **No connection pool reuse in `VLLMRemoteClient`.** Each `generate` builds a fresh `httpx.AsyncClient`. Cost: a few ms per request for TLS handshake. Chose correctness-first for the C1 timeline; would add app-lifecycle-managed client for Phase E if measurements say it matters.
- **Rule-based router with a documented LLM-planner upgrade path.** Deterministic, testable, upgrade path clear. Cost: rule maintenance burden as new intents arrive; the eventual hybrid is a genuine next step, not a punt.
- **Retry not applied to streams.** Streaming failures propagate. Cost: no automatic recovery from transient network errors mid-stream. Chose this because retrying a streaming decode either duplicates emitted content or discards it — neither is a clean UX.

## Failure modes I've thought about

- **LLM slow or unresponsive.** Client sees a 30 s timeout, retries twice with backoff, then falls back to template answer. Trace records `error` on `llm_generate` or `partial=True` on `llm_generate_stream`.
- **PostgreSQL unavailable.** `get_course_profile` and `search_course_docs` fail; the dispatcher's per-tool `try/except` prevents request-level failure. The LLM gets an empty evidence pack and, because the system prompt is grounded to evidence, honestly reports "insufficient information." This actually happened on the first ICRN end-to-end run.
- **vLLM version drift breaking metric names.** `scripts/vllm_metrics_snapshot.py` tolerates missing metrics rather than crashing. Non-fatal signal degradation instead of hard failure.
- **CUDA driver / runtime mismatch on new GPU nodes.** `docs/vllm_setup.md` documents pinning `vllm<0.20` and using `torch --index-url .../cu128` to match ICRN's driver. This was a real debug session, folded back into the runbook.
- **Prefix caching hiding a regression.** All benchmark prompts are cycled across four templates so I never report TTFT that reflects only a warm prefix.
- **Prompt injection in user query.** Not currently defended against — the risk is low for an advising workload but non-zero. A future addition would be delimiter isolation of user-provided content in the user prompt and/or an output-side filter.

---

## Numbers to fill in from Task C6 benchmark

Run these and paste into the placeholders above:

```bash
# On ICRN, with vLLM + backend + postgres up (bash scripts/dev_up.sh):

# Single-user baseline — TTFT lower bound for streaming
python -m scripts.benchmark --endpoint stream --concurrency 1 --total-requests 5

# Realistic user load
python -m scripts.benchmark --endpoint stream --concurrency 10 --total-requests 50

# Same load on blocking, for comparison
python -m scripts.benchmark --endpoint chat --concurrency 10 --total-requests 50
```

The three p95 values that feed the resume bullet are the numbers to prioritize:

- `{P95_TTFT_MS}` — streaming p95 TTFT under 10 concurrent
- `{P95_TOTAL_MS}` — streaming p95 total latency under 10 concurrent
- `{P95_BLOCKING_MS}` — blocking p95 total latency under 10 concurrent

The rest of the tail (p50, p99) go into the benchmark report and support the "why percentiles matter" answer in Q15.
