# IlliniGuide Serve — Truthful Delivery Roadmap

**Last reviewed:** 2026-07-13

**Project status:** a demonstrable AI-serving prototype; not yet a fully observable, evaluated, or deployable production system.

This roadmap is deliberately evidence-first. A feature can be implemented in code while still being **Partial** until it has a reproducible run, saved artifact, and documentation that match. Never promote a target metric into a resume bullet before its resume gate is passed.

## Status legend

| Status | Meaning |
|---|---|
| Implemented | Code is present and its primary path has been verified. |
| Partial | Code or an initial run exists, but scope, reproducibility, or validation is incomplete. |
| Planned | No verified implementation or deployment evidence yet. |
| Target | A desired future result. It must never be described as an observed result. |

## Current baseline: what is true today

| Area | Status | Verified baseline / boundary |
|---|---|---|
| Backend layering and structured tools | Implemented | FastAPI route -> router -> dispatcher -> tools -> answer synthesis; backend suite previously passed 223 tests. |
| PostgreSQL schema | Implemented | `courses`, `gpa_stats`, `course_chunks`, evaluation tables, and pgvector initialization exist. |
| Course data | Partial | Local data contains about 80 ECE courses and 20 GPA rows; catalog coverage is incomplete. |
| Semantic RAG code | Partial | Section chunking, MiniLM embedding client, pgvector cosine retrieval, metadata filter, keyword fallback, and low-confidence note exist. A live retrieval-quality report is still missing. |
| LLM serving | Implemented | Self-hosted **Qwen2.5-7B-Instruct** on one ICRN H200 through vLLM, `float16`, 8K context, prefix caching. |
| Streaming UI | Implemented | Backend SSE and frontend incremental rendering/cancellation exist; the frontend production build has passed. |
| Load benchmark | Partial | A 10-concurrency run recorded streaming p50 TTFT 55 ms and blocking p50 472 ms. Saved results do not yet establish tokens/sec, error rate, or GPU compute utilization. |
| Observability | Partial | Per-tool debug trace and a vLLM `/metrics` snapshot script exist; no Prometheus scrape, Grafana dashboard, or application metrics endpoint is verified. |
| Docker | Partial | Dockerfiles are uncommitted WIP and lack a clean-environment compose smoke test. |
| Kubernetes | Planned | `infra/k8s/` has no manifests or recovery evidence. |
| Evaluation | Partial | A frozen 34-case retrieval harness, semantic/keyword comparison, and artifact schema exist; no live DB run or saved quality result exists. |

## Resume claim gates

These are targets, not current accomplishments.

| Desired claim | Current truth | Required evidence before writing it |
|---|---|---|
| “served Qwen3-32B (BF16)” | The verified serving model is Qwen2.5-7B-Instruct FP16. | Exact launch configuration, `/v1/models` output, smoke test, model-specific benchmark JSON/CSV, and a commit/docs update. |
| “10+ concurrent requests” | Exactly 10 concurrent requests have been benchmarked. | At least one saved, reproducible run at the claimed concurrency; report the exact value, not `+` unless several higher levels pass. |
| “indexes 150+ department courses” | About 80 ECE course records are evidenced. | Source inventory, ingestion report showing >=150 deduplicated records, and persisted chunks/embeddings counts. |
| “92% answer relevance” | No labeled evaluation or recorded result supports this number. | Frozen question set, relevance rubric, independent labels, evaluation script output, denominator, and a versioned report. |
| “65–70% GPU utilization” | `--gpu-memory-utilization 0.85` is only a vLLM VRAM allocation cap, not GPU compute utilization. | Time-series sampling during a named load run, sampling method, aggregation window, raw CSV, and comparison baseline. |

## Phase 0 — Reconcile project documentation

**Status:** Implemented

**Effort:** half day

**Why first:** the README, RAG design, and demo material currently contain older status claims that conflict with the code and benchmark evidence.

### Tasks

- [x] Add a single `Implemented / Partial / Planned` table to `README.md` using the current-baseline table above.
- [x] Update `docs/architecture.md` to show frontend SSE, vLLM serving, and semantic RAG code as their actual statuses.
- [x] Update `docs/rag_design.md`: distinguish implemented code paths from the still-missing live quality evaluation.
- [x] Update `docs/llm_serving_design.md` and `docs/demo_script.md` so the active, evidenced model is Qwen2.5-7B-Instruct FP16—not Qwen3-32B.
- [x] Mark Docker as WIP/unverified and Kubernetes as planned in every status table.
- [x] Link this roadmap from `README.md` after review.

### Acceptance evidence

- [x] A reviewer can read README, architecture, RAG, serving, and demo docs without finding contradictory feature status.
- [x] Every retained historical resume number in these docs links to its command shape and evidence limitation; unmeasured targets remain explicitly labeled.

### Interview takeaway

> “I separate implemented code from operational proof. For serving systems, a benchmark or dashboard claim is not complete until its raw artifact is reproducible.”

## Phase 1 — Expand and validate the RAG corpus

**Status:** Partial — code and test harnesses are implemented; all live corpus, real MiniLM, and scored-evaluation evidence remains pending.

**Effort:** 1–2 days

**Dependency:** Phase 0 documents the current 80-course baseline accurately.

### 1A. Build a 150-course data gate

- [ ] Select official UIUC ECE/CS source pages and document provenance, fetch date, and licensing/usage boundaries in `docs/data_sources.md`.
- [ ] Extend ingestion until it produces at least 150 **deduplicated** course records. Do not count chunks as courses.
- [ ] Record course counts by department and missing/failed source rows.
- [ ] Add tests for duplicate course IDs, missing source URLs, malformed prerequisites, and idempotent re-ingestion.
- [ ] Persist the ingestion report under a versioned `artifacts/` or `docs/results/` directory (to be created in its own PR).

### 1B. Run real semantic embedding ingestion

Use the real embedding backend rather than the mock default:

```bash
cd backend
EMBEDDING_BACKEND=sentence_transformer \
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \
python -m scripts.ingest_embeddings
```

- [ ] Save stdout plus course/chunk/embedding counts.
- [ ] Confirm the `course_chunks.embedding` dimension and pgvector index agree with the embedding model.
- [ ] Manually inspect ten retrievals: exact course query, cross-course semantic query, unsupported query, and metadata-filtered query.

### 1C. Create a defensible retrieval evaluation

- [ ] Create 30–50 advisor-style retrieval queries with expected course IDs/chunk IDs and source citations.
- [ ] Define the rubric before scoring: evidence recall, citation correctness, and correct low-confidence fallback are separate labels.
- [ ] Run the existing evaluation entry point against the live DB:

```bash
cd backend
EMBEDDING_BACKEND=sentence_transformer \
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \
python -m scripts.eval_retrieval
```

- [ ] Save exact question-set version, model ID, top-k, metadata-filter policy, raw per-query outputs, and aggregate Recall@k/citation metrics.
- [ ] Compare pgvector retrieval with the keyword fallback using the same questions.
- [ ] Write `docs/evaluation_plan.md` and a first `docs/benchmark_report.md` only after results exist.

### Resume gate

Only after 1A passes may the resume say “indexed 150+ department courses.” Only after 1C passes may it state an observed relevance percentage; report the metric definition, e.g. “92% evidence Recall@3 on a 40-query labeled retrieval set,” rather than the vague phrase “answer relevance.”

### Interview takeaway

> “Structured course facts such as prerequisites and GPA use deterministic tools; unstructured descriptions use cited pgvector retrieval. I evaluate retrieval quality separately from generation quality.”

## Phase 2 — Finish observability and GPU telemetry

**Status:** Planned

**Effort:** 1–2 days

**Dependency:** preserve the existing `ToolTraceCollector` as the source of per-tool timing/status.

### 2A. Application metrics

- [ ] Add a minimal Prometheus metrics endpoint without bypassing the route/service layering.
- [ ] Record request count and error count by endpoint/status.
- [ ] Record histograms for end-to-end latency, retrieval latency, each tool latency, LLM latency, and streaming TTFT.
- [ ] Record tool success/failure counters by tool name.
- [ ] Add service-level tests covering success, failure, missing metadata, and histogram observation.

### 2B. vLLM and GPU metrics

- [ ] Configure Prometheus to scrape vLLM `/metrics`; retain `backend/scripts/vllm_metrics_snapshot.py` as a lightweight manual diagnostic.
- [ ] Capture prompt/generation throughput, TTFT, waiting queue depth, and KV-cache utilization.
- [ ] Add a controlled GPU sampling method: DCGM exporter when available, otherwise timestamped `nvidia-smi` sampling for utilization and memory usage.
- [ ] Store the sampler cadence, command/version, start/end timestamps, and raw CSV alongside each benchmark.
- [ ] Create one Grafana dashboard showing app latency/errors alongside vLLM queue/KV-cache and GPU utilization.

### Non-negotiable metric definitions

- **GPU utilization** = sampled GPU compute utilization over a stated interval; it is not `--gpu-memory-utilization`.
- **GPU memory usage** = allocated/used VRAM; report separately from compute utilization.
- **Error rate** = failed counted requests / all counted requests, including timeouts and malformed streams.
- **Tokens/sec** = define whether it is aggregate generation throughput or per-request output throughput; never mix the two.

### Resume gate

The phrase “observed 65–70% GPU utilization” is allowed only if the raw samples come from the same named load test, the aggregation (for example, mean over the steady-state window) is stated, and the comparison baseline uses identical prompt/output distributions.

## Phase 3 — Reproducible benchmark and model-migration gate

**Status:** Planned

**Effort:** 1–2 days

**Dependency:** Phase 2 telemetry for resume-grade utilization/error/throughput claims.

### 3A. Standard benchmark matrix

- [ ] Add an output option to `backend/scripts/benchmark.py` that writes raw per-request JSON/CSV and a run manifest. Do not rely on copied terminal text.
- [ ] Capture the git commit, model ID, vLLM version, launch flags, embedding model, dataset version, request timeout, warmup, prompt set, and timestamp for each run.
- [ ] Run and save the following matrix:

| Scenario | Endpoint | Configuration | Required interpretation |
|---|---|---|---|
| Warm single-user baseline | stream | concurrency 1, warmup 15 | best-case TTFT and total latency |
| Warm steady state | stream + blocking | concurrency 10, warmup 15, counted requests 60 | p50/p95/p99 TTFT and end-to-end latency |
| Cold burst | stream | concurrency 10 immediately after server start | first-cohort queue/prefill tail |
| Saturation probe | stream | concurrency 20 then 30 | queue depth, KV cache, utilization, errors, and safe limit |

- [ ] Publish a table with p50/p95/p99 total latency and TTFT, aggregate tokens/sec, error rate, average/peak GPU compute utilization, memory usage, queue depth, and KV-cache utilization.
- [ ] Separate cold-burst data from warm steady-state data; never average them into one flattering percentile.

### 3B. Qwen3-32B BF16 migration gate

**Current status:** Target. The documented baseline is Qwen2.5-7B-Instruct FP16; do not replace it in the resume or docs before this gate succeeds.

- [ ] Preserve a complete 7B baseline result before changing model configuration.
- [ ] Confirm current ICRN H200 availability and policy allow the planned memory reservation; this is a shared resource.
- [ ] Create a focused serving change that makes the model explicit via environment variable and documents the exact Qwen3-32B BF16 configuration, context length, GPU memory cap, and tensor-parallel size.
- [ ] Start the server, capture `/v1/models`, run `scripts.verify_vllm`, and retain startup logs.
- [ ] Verify backend handling of Qwen3 reasoning/non-thinking response behavior before using it for advising output.
- [ ] Run the full matrix in 3A for Qwen3-32B and compare it with the 7B baseline using the same prompts and load profile.
- [ ] Record failures, OOM behavior, queueing threshold, and quality tradeoff. Revert to the 7B baseline if the larger model has no demonstrated workload benefit.

### Resume gate

Only after 3B succeeds can the model phrase become:

> “Served Qwen3-32B (BF16) on a single H200 via vLLM …”

Do not add “high-throughput” without the matching saved tokens/sec result. Do not claim “10+ concurrent requests” when only concurrency 10 passed; write the maximum verified concurrency exactly.

## Phase 4 — Docker Compose reproducibility

**Status:** Planned

**Effort:** half to one day

**Dependency:** current Docker files are WIP and must remain labeled unverified until this phase passes.

- [ ] Review and commit focused backend/frontend Dockerfiles, `.dockerignore` files, and Nginx configuration after verification.
- [ ] Complete a Compose stack for frontend, backend, and PostgreSQL; document how vLLM is reached in local CPU-only versus ICRN GPU environments.
- [ ] Verify Nginx does not buffer SSE responses.
- [ ] From a clean environment, build images and run health check, blocking chat, streaming chat, compare, and recommend smoke tests.
- [ ] Save command output and image tags; add a concise manual verification section to the README.

## Phase 5 — Kubernetes basic reliability

**Status:** Planned

**Effort:** later-stage work

**Dependency:** Phase 4 reproducible container images and a real Kubernetes namespace. ICRN notebooks alone are not a user-managed Kubernetes cluster.

- [ ] Add backend Deployment/Service, frontend Deployment/Service/Ingress, ConfigMap, and Secret manifests.
- [ ] Add readiness and liveness probes; document why readiness protects traffic and liveness triggers recovery.
- [ ] Demonstrate a rolling update and capture the result.
- [ ] Kill a backend pod and verify recovery and request behavior.
- [ ] Run a single vLLM replica first; add GPU scheduling only when the cluster exposes GPU resources.
- [ ] Defer HPA until Phase 2 and Phase 3 provide meaningful queue/latency/utilization signals.

## Suggested PR sequence

1. `docs: reconcile current implementation status and roadmap`
2. `test: add corpus-ingestion edge cases and retrieval evaluation dataset`
3. `feat: export reproducible retrieval-evaluation artifacts`
4. `feat: add Prometheus metrics for requests, TTFT, tools, and errors`
5. `feat: persist benchmark runs and GPU telemetry`
6. `feat: evaluate Qwen3-32B serving configuration on H200`
7. `chore: verify Docker Compose from a clean environment`
8. `feat: add baseline Kubernetes manifests and recovery checks`

## Final resume-safe wording today

Use this until the corresponding gates pass:

> Built a self-hosted AI academic-advising prototype on a UIUC H200, serving Qwen2.5-7B-Instruct through vLLM and FastAPI. Implemented structured academic tools, citation-oriented retrieval, and SSE streaming; benchmarked client-observed streaming behavior at 10-way concurrency.

Avoid today: Qwen3-32B BF16, 150+ courses, 92% relevance, 65–70% GPU utilization, tokens/sec, and error-rate numbers. Those are valuable next milestones, not current facts.
