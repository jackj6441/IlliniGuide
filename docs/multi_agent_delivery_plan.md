# IlliniGuide Serve — Multi-Agent Delivery Plan

**Source roadmap:** [todo_roadmap.md](todo_roadmap.md)

**Operating principle:** use multiple agents to prepare independent, reviewable changes in parallel; run shared databases, the H200, and status-document updates in controlled sequence.

This plan preserves the roadmap's evidence-first rule. Qwen3-32B BF16, 150+ courses, 92% relevance, 65–70% GPU utilization, tokens/sec, and error-rate figures remain **Targets** until their corresponding raw artifacts are reviewed by the coordinator.

## 1. Team topology

| Role | Responsibility | May change | Must not change |
|---|---|---|---|
| **Coordinator** | Owns scope, status vocabulary, integration order, live-run approval, and resume gates. | `docs/todo_roadmap.md`, this plan, final status/docs integration. | Does not delegate final truth/status decisions. |
| **Docs Agent A** | Reconciles public architecture/demo/README status. | `README.md`, `docs/architecture.md`, `docs/demo_script.md` | `docs/rag_design.md`, `docs/llm_serving_design.md` |
| **Docs Agent B** | Reconciles RAG and LLM-serving design claims. | `docs/rag_design.md`, `docs/llm_serving_design.md` | README and general architecture docs |
| **Corpus Agent** | Extends source-tagged ECE/CS course ingestion. | ingestion modules/scripts/tests, `docs/data_sources.md` | embedding/evaluation code and Docker WIP |
| **Embedding Agent** | Makes real MiniLM ingestion and integrity verification reproducible. | embedding modules/scripts/tests | source ingestion and evaluation labels |
| **Evaluation Agent** | Creates frozen retrieval cases and evaluation artifacts. | retrieval evaluation modules/tests/cases/docs | ingestion/embedding implementation |
| **App Metrics Agent** | Exposes application-level metrics from the existing trace boundary. | new observability module, app wiring, targeted tests | vLLM scripts, benchmark script, Docker WIP |
| **Telemetry Agent** | Captures vLLM/GPU telemetry and dashboard/scrape assets. | vLLM snapshot, GPU sampler, `infra/prometheus/`, `infra/grafana/` | application route/service behavior |
| **Benchmark & Model Agent** | Persists benchmark artifacts and prepares the Qwen3 model gate. | `backend/scripts/benchmark.py`, benchmark tests, `scripts/dev_up.sh`, benchmark docs | trace internals and telemetry collector format |
| **Compose Agent** | Owns the current Docker WIP through clean-environment verification. | Compose/Docker/Nginx files only | README and Kubernetes manifests |
| **Kubernetes Agent** | Adds baseline manifests and recovery checks after Compose passes. | `infra/k8s/**` only | Docker/Compose files and model configuration |

### Concurrency rule

At most three implementation agents should work at once, plus the coordinator. Each agent owns a disjoint file set. If a task needs a file owned by another active agent, it creates a short handoff request instead of editing that file.

## 2. Universal collaboration contract

Every agent starts its PR description with:

```markdown
Goal:
Owned files:
Inputs/dependencies:
Out of scope:
Verification:
Artifacts produced:
Resume/status impact:
```

Every agent ends with:

```markdown
Implemented / Partial / Blocked:
Commands run and results:
Files changed:
Artifact paths and checksums/metadata:
Known limitations:
Handoff required from / to:
```

### Shared conventions

- One focused Conventional Commit per agent PR.
- Tests use fixtures and stubs; no test depends on live UIUC pages, ICRN, or the H200.
- Runtime evidence is immutable and namespaced: `artifacts/<kind>/<UTC-timestamp>-<short-git-sha>/`.
- Each artifact manifest records UTC start/end time, git SHA, command, environment/model version, input data version, and output file list.
- No secrets, tokens, private course data, or raw credentials enter artifacts or Git.
- A feature status changes only during coordinator integration, never inside an implementation PR.

## 3. Dependency map

```text
Wave 0: documentation reconciliation
        |
        +--> Wave 1A: corpus preparation -----------+
        |                                            |
        +--> Wave 1B: embedding verification prep ---+--> live corpus -> live embeddings -> retrieval evaluation
        |                                            |
        +--> Wave 1C: evaluation dataset/harness ----+
        |
        +--> Wave 2A: application metrics -----------+
        |                                            |
        +--> Wave 2B: vLLM/GPU telemetry ------------+--> reproducible 7B benchmark -> Qwen3-32B gate
        |                                            |
        +--> Wave 2C: benchmark artifact writer -----+
        |
        +--> Wave 3: Compose verification -> Wave 4: Kubernetes manifests/recovery
```

The arrows represent **evidence dependencies**, not necessarily code-preparation dependencies. For example, the Evaluation Agent may write the labeled retrieval cases while the Corpus Agent is still extending ingestion, but cannot publish a scored live result until real embeddings are present.

## 4. Wave 0 — Documentation reconciliation

**Objective:** make the repository narrative match the current prototype before new metrics or deployment claims appear.

### Parallel assignments

| Agent | Owned files | Acceptance |
|---|---|---|
| Docs Agent A | `README.md`, `docs/architecture.md`, `docs/demo_script.md` | Frontend SSE, tool pipeline, vLLM baseline, and benchmark are accurately described; Docker is Partial, K8s Planned; roadmap links are present. |
| Docs Agent B | `docs/rag_design.md`, `docs/llm_serving_design.md` | Semantic pgvector code is distinguished from missing live quality evaluation; Qwen2.5-7B FP16 is current evidence and Qwen3-32B BF16 is Target. |

### Coordinator integration checklist

- [ ] No stale wording says frontend, vLLM, or all RAG is merely planned/mock.
- [ ] No document says Qwen3-32B has run.
- [ ] No unmeasured GPU utilization, 150-course, or relevance percentage appears as a result.
- [ ] `git diff --check` passes.

**Handoff:** Docs Agents notify all later agents of final status vocabulary. Only then can later reports link to the canonical docs.

## 5. Wave 1 — RAG corpus and retrieval validation

**Objective:** turn “semantic RAG code exists” into a reproducible, evaluated retrieval system without conflating retrieval with LLM answer quality.

### 1A. Parallel implementation preparation

| Agent | Owned files | Inputs | Deliverable / acceptance |
|---|---|---|---|
| Corpus Agent | `backend/app/ingestion/ece_prereqs.py`, `backend/scripts/ingest_ece_prereqs.py`, new CS ingestion module/script, ingestion tests, `docs/data_sources.md` | Official ECE/CS source URLs and saved HTML fixtures | Deduplicated source-tagged ingestion and `artifacts/ingestion/<run-id>/manifest.json`; tests cover duplicates, malformed IDs/prereqs, missing source URL, idempotence. |
| Embedding Agent | `backend/app/ingestion/embed_chunks.py`, `backend/scripts/ingest_embeddings.py`, embedding tests, new verification script | Existing 384-d pgvector schema and expected MiniLM config | Real-ingestion manifest records backend/model/dimension/course/chunk count; integrity checks catch no vectors and wrong dimensions. |
| Evaluation Agent | `backend/app/services/rag/eval.py`, `backend/scripts/eval_retrieval.py`, evaluation tests, versioned retrieval case fixtures, `docs/evaluation_plan.md` | Current retriever API and planned artifact convention | Frozen 30–50-case harness with Recall@1/@k, citation correctness, section correctness, low-confidence correctness, and pgvector-vs-keyword comparison. |

### 1B. Sequential live execution

1. **Corpus gate:** Coordinator merges and runs Corpus Agent work. `COUNT(DISTINCT course_id) >= 150` must be proven by its ingestion manifest.
2. **Embedding gate:** Coordinator runs real MiniLM ingestion only against the approved corpus:

   ```bash
   cd backend
   EMBEDDING_BACKEND=sentence_transformer \
   EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \
   python -m scripts.ingest_embeddings
   ```

3. **Evaluation gate:** Coordinator runs the frozen cases against the verified embedding corpus, then publishes raw per-query and aggregate results.

### Resume/status gate

- “150+ department courses” requires the Corpus Agent's **live** manifest; chunks do not count as courses.
- “92% relevance” is forbidden unless it is replaced with the exact observed metric, numerator/denominator, question-set version, and raw evaluation artifact.
- The coordinator must state whether the score measures retrieval evidence, citations, or generated answers—they are not interchangeable.

## 6. Wave 2 — Observability, benchmark artifacts, and Qwen3 gate

**Objective:** bind user-facing request outcomes, vLLM server behavior, and GPU behavior to the same reproducible benchmark run.

### 2A. Parallel implementation preparation

| Agent | Owned files | Deliverable / acceptance |
|---|---|---|
| App Metrics Agent | New `backend/app/observability.py`, app wiring, `backend/app/services/advising_service.py`, targeted tests, dependency metadata | Prometheus text endpoint; request/error counters; E2E/retrieval/tool/LLM/TTFT histograms; tool success/failure counters. No high-cardinality labels such as prompt, course ID, request ID, or raw error. |
| Telemetry Agent | `backend/scripts/vllm_metrics_snapshot.py`, new `backend/scripts/gpu_sampler.py`, `infra/prometheus/`, `infra/grafana/dashboards/`, telemetry note | Timestamped GPU CSV plus vLLM scrape configuration and dashboard. Must distinguish GPU compute utilization, VRAM usage, and KV-cache usage. |
| Benchmark & Model Agent | `backend/scripts/benchmark.py`, benchmark tests, `scripts/dev_up.sh`, benchmark artifact schema/docs | `--output-dir` or equivalent raw JSON/CSV plus run manifest; exact model/dtype/context/VRAM/TP config; no model behavior/parser change in this PR. |

### Handoff contract

1. App Metrics Agent publishes final metric names and labels.
2. Telemetry Agent configures Prometheus/Grafana against those names and defines GPU CSV columns/cadence.
3. Benchmark & Model Agent records telemetry file references and run timestamps inside each benchmark manifest.
4. Coordinator runs the matrix and validates that all three sources cover the same interval.

### Required benchmark matrix

| Scenario | Requirement |
|---|---|
| Warm single user | stream, concurrency 1, warmup 15 |
| Warm steady state | stream and blocking, concurrency 10, warmup 15, 60 counted requests |
| Cold burst | stream, concurrency 10 immediately after server start |
| Saturation probe | stream, concurrency 20 then 30; record queue/KV-cache/errors |

### Metric contract

- **GPU utilization:** sampled GPU compute utilization for a stated steady-state time window. It is not `--gpu-memory-utilization`.
- **Error rate:** failed counted requests divided by all counted requests; includes timeouts and malformed SSE.
- **Tokens/sec:** label source explicitly—vLLM aggregate generation throughput or documented client-side approximation.
- **TTFT:** record streaming client-observed TTFT separately from total latency and cold-burst tail.

### Qwen3-32B BF16 model-migration gate

This is a coordinator-approved execution step after a reproducible Qwen2.5-7B FP16 baseline exists.

1. Confirm ICRN H200 allocation/availability and shared-resource constraints.
2. Record exact model ID, dtype, context length, GPU memory cap, and tensor-parallel size in the launch command.
3. Save vLLM startup log, `/v1/models` response, and `python -m scripts.verify_vllm` output.
4. Capture a real Qwen3 streaming payload before changing response parsing; current code may not consume reasoning-specific delta fields.
5. Run the identical matrix for 7B and 32B; retain OOMs, queue thresholds, quality observations, and failure data.
6. If the larger model has no demonstrated advising-workload benefit, restore the 7B baseline rather than claiming an upgrade.

### Resume/status gate

| Claim | Coordinator must review |
|---|---|
| “served Qwen3-32B BF16” | launch config, startup log, `/v1/models`, smoke response, and model-specific run manifest |
| “10+ concurrent requests” | raw request files for every claimed concurrency; write exact maximum verified concurrency |
| “high-throughput / X tok/s” | token source, run-clock interval, vLLM telemetry, model/configuration, raw data |
| “65–70% GPU utilization” | same-run GPU CSV, aggregation window, prompt-identical baseline comparison |
| p95 latency / error rate | counted-request denominator and cold-versus-warm separation |

## 7. Wave 3 — Docker Compose verification

**Objective:** prove a clean, reproducible portable stack without treating current uncommitted Docker files as completed work.

### Single-owner assignment

The Compose Agent alone owns:

- `docker-compose.yml`
- `backend/Dockerfile` and `backend/.dockerignore`
- `frontend/Dockerfile`, `frontend/.dockerignore`, and `frontend/nginx.conf.template`

Because these files are currently user-owned WIP, the Coordinator must explicitly confirm the baseline with the owner before the agent changes them.

### Acceptance

- [ ] `docker compose config` succeeds.
- [ ] A clean build starts frontend, backend, and PostgreSQL.
- [ ] Use the mock LLM for portable Compose smoke tests; document external ICRN vLLM injection separately.
- [ ] Verify health, blocking chat, unbuffered SSE through Nginx, compare, and recommend.
- [ ] Publish sanitized logs, image tags, command transcript, and service configuration contract.

**Handoff to Wave 4:** image tags, exposed ports, required environment variables, `GET /health`, proxy behavior for `/api/*` and `/api/chat/stream`, and DB initialization/seed procedure.

## 8. Wave 4 — Kubernetes basic reliability

**Entry gate:** Wave 3 passes and the user provides a real Kubernetes namespace with verified `kubectl` permissions. ICRN notebook storage access alone does not satisfy this gate.

### Single-owner assignment

The Kubernetes Agent owns `infra/k8s/**` only.

### Sequence and acceptance

1. Add backend Deployment/Service and frontend Deployment/Service/Ingress, ConfigMap, and secret template without secret values.
2. Add readiness/liveness probes using the validated backend health endpoint.
3. Run server-side dry run, rollout, and a rolling-update check.
4. Kill a backend pod and save recovery/request-behavior evidence.
5. Consume external vLLM by configuration first. Add a GPU vLLM workload only after the cluster exposes GPU scheduling resources.
6. Defer HPA until Wave 2 has useful queue, latency, error, and utilization signals.

Kubernetes is **Implemented** only after rollout and recovery evidence—not when YAML merely exists.

## 9. Coordinator review cadence

| Checkpoint | Required review |
|---|---|
| After each PR | Owned-file boundary respected, focused tests pass, no status inflation. |
| Before each live run | Correct git SHA, immutable run ID, input/model versions, artifact destination, and rollback path. |
| After live RAG/benchmark run | Inspect raw data before editing reports or resume text. |
| Before Docker/Kubernetes status promotion | Clean-environment or cluster evidence is attached. |

## 10. Recommended execution schedule

| Wave | Concurrent agents | Coordinator action | Merge/run order |
|---|---|---|---|
| 0 | Docs A + Docs B | Reconcile status vocabulary | Merge together after cross-review |
| 1 preparation | Corpus + Embedding + Evaluation | **Partial:** code/test harnesses integrated; no live evidence | Commit isolated PRs; run corpus -> embeddings -> evaluation sequentially |
| 2 preparation | App Metrics + Telemetry + Benchmark/Model | Freeze metric and manifest contract | Merge metrics -> telemetry -> benchmark writer; run 7B matrix -> 32B gate |
| 3 | Compose only | Protect Docker WIP ownership | Clean Compose verification |
| 4 | Kubernetes only | Verify namespace/permissions | Apply -> rollout -> pod-recovery test |

## 11. Interview explanation

> “I used multi-agent development as a dependency-aware delivery process, not as parallel code generation. Independent agents owned isolated modules, while the coordinator serialized shared live resources—the course database, H200 GPU, benchmark artifact schema, and status documentation. That let us move quickly without mixing unverified targets into the project narrative.”
