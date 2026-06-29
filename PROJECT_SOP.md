# IlliniGuide Serve Project SOP

## 0. Project Summary

**Project Name:** IlliniGuide Serve

**One-line positioning:**

> A self-hosted LLM/RAG serving platform for UIUC ECE/CS academic advising workloads, built with FastAPI, React, vLLM, PostgreSQL/pgvector, Prometheus/Grafana, and later Kubernetes reliability experiments.

**Main goal:**

Build a real AI infra / LLM serving project, not a simple LangChain chatbot.
The UIUC ECE/CS advising scenario is the workload/demo, but the main technical value is the serving platform, RAG pipeline, tool orchestration, observability, and benchmark infrastructure.

---

## 1. Core Design Principles

### 1.1 What this project is

This project is:

* A self-hosted LLM serving + RAG platform.
* An academic advising workload for UIUC ECE/CS courses.
* A system that combines:

  * structured course database,
  * vector retrieval,
  * tool calling,
  * LLM reasoning/explanation,
  * metrics and benchmarks.

### 1.2 What this project is not

This project is not:

* a simple OpenAI API wrapper,
* a pure LangChain demo,
* a professor ranking or attack system,
* a replacement for official academic advisors,
* a full degree audit system,
* a mobile app,
* a production auth/payment system,
* a full fine-tuning project.

### 1.3 LLM role vs tool role

The LLM should not blindly recommend courses.

Correct design:

```text
LLM = intent understanding + tool planner + evidence synthesis + advisor-style response
Tools = reliable computation + database lookup + retrieval + scoring
```

Example:

```text
User: I want AI infra. Should I take ECE 408 or CS 433?

System:
1. Detect intent: course comparison + career direction.
2. Retrieve course documents for ECE 408 and CS 433.
3. Query structured course database.
4. Query GPA/instructor stats if available.
5. Compare direction match.
6. Generate grounded answer with citations.
```

---

## 2. Version Roadmap

### Version 1: Working Advising RAG App

Goal: make the system work end-to-end.

Features:

* React chat page.
* Course comparison page.
* FastAPI backend.
* PostgreSQL + pgvector.
* Basic course ingestion.
* RAG retrieval.
* vLLM endpoint support.
* external API fallback only for development/debug.
* citations with URL/snippet.
* simple evaluation dataset.

No Kubernetes or failure injection yet.

---

### Version 2: Tool Calling + Structured Advising

Goal: upgrade from normal RAG to an advising system.

Features:

* manual tool router.
* tools:

  * `search_course_docs`
  * `get_course_profile`
  * `get_gpa_stats`
  * `check_prerequisites`
  * `compare_courses`
  * `recommend_courses`
* simple fixed pipeline for easy queries.
* LLM planner for complex queries.
* debug-mode tool trace.
* recommendation score hidden from normal UI but available in debug/API.

---

### Version 3: LLM Serving + Observability

Goal: make the project clearly AI infra.

Features:

* vLLM OpenAI-compatible server.
* streaming response.
* continuous batching benchmark.
* KV cache / token throughput discussion.
* Prometheus metrics.
* Grafana dashboard.
* latency breakdown:

  * retrieval latency,
  * tool latency,
  * prefill latency,
  * decode latency,
  * total latency.
* load testing with 10–20 concurrent users first.
* later stretch to 100+ concurrent users.

---

### Version 4: Kubernetes + Reliability Experiments

Goal: build the strong resume version.

Features:

* Kubernetes deployment.
* readiness/liveness probes.
* rolling update.
* HPA.
* vLLM pod recovery.
* vector DB unavailable fallback.
* timeout/retry/fallback.
* failure injection report.
* serving benchmark report.

---

## 3. Target Tech Stack

### Frontend

* React
* TypeScript preferred
* Vite preferred
* Tailwind optional

### Backend

* FastAPI
* Python 3.11+
* Pydantic
* SQLAlchemy or SQLModel
* async endpoints where useful

### Database

* PostgreSQL
* pgvector extension

Use PostgreSQL for both:

* structured academic data,
* vector embeddings.

### LLM Serving

Primary:

* vLLM OpenAI-compatible API server.

Development fallback:

* mock OpenAI-compatible endpoint,
* external API fallback only for debugging.

### Embeddings

Use a configurable embedding model.

Environment variable:

```bash
EMBEDDING_MODEL_NAME=
```

Do not hardcode one provider. The embedding provider should be swappable.

### Observability

Version 3+:

* Prometheus
* Grafana
* OpenTelemetry later

### Deployment

Version 1:

* local development
* Docker Compose

Version 3:

* Colab GPU or school GPU
* vLLM remote endpoint

Version 4:

* Kubernetes on local cluster / school cloud GPU if available

---

## 4. Data Scope

### 4.1 First version course coverage

Initial scope:

* ECE + CS core courses.
* 30–50 courses.
* Do not attempt full course catalog at first.
* Expand to full ECE/CS only after the system is stable.

### 4.2 Data sources

Initial data sources:

1. UIUC course catalog
2. HKN ECE Course Wiki
3. Grade Disparities by Instructor
4. UIUC prerequisite-related pages or scraped prerequisite information

Rules:

* Store source URL for every document.
* Store raw fetched data where legally/ethically appropriate.
* Use reasonable request rate limits.
* Do not build aggressive scraping.
* Prefer reproducible ingestion scripts.

### 4.3 Core course fields

Each course should contain:

```text
course_id
department
number
title
description
credit_hours
prerequisites
source_url
career_tags
created_at
updated_at
```

GPA/instructor data should contain:

```text
course_id
instructor_name
term
average_gpa
grade_distribution
source_url
```

Career tags are useful for recommendation but can be manually labeled in v1.

Example tags:

```text
ai_ml
ai_infra
systems
software_engineering
computer_architecture
data_science
robotics_cv
security
```

---

## 5. Repository Structure

Use this structure unless there is a strong reason to change it.

```text
illiniguideserve/
  README.md
  PROJECT_SOP.md
  docker-compose.yml
  .env.example

  backend/
    pyproject.toml
    app/
      main.py
      config.py
      db/
        session.py
        models.py
        migrations/
      api/
        chat.py
        courses.py
        compare.py
        recommend.py
        health.py
        metrics.py
      services/
        rag/
          chunker.py
          embedder.py
          retriever.py
          reranker.py
          citation.py
        llm/
          client.py
          prompt_templates.py
          streaming.py
        tools/
          router.py
          schemas.py
          course_tools.py
          gpa_tools.py
          prereq_tools.py
          compare_tools.py
          recommend_tools.py
        evaluation/
          eval_runner.py
          metrics.py
      ingestion/
        ingest_catalog.py
        ingest_hkn.py
        ingest_gpa.py
        ingest_prereqs.py
        normalize.py
      tests/
        test_rag.py
        test_tools.py
        test_api.py

  frontend/
    package.json
    src/
      main.tsx
      App.tsx
      pages/
        ChatPage.tsx
        ComparePage.tsx
      components/
        ChatBox.tsx
        MessageBubble.tsx
        CitationList.tsx
        ToolTracePanel.tsx
        CourseCompareCard.tsx
      api/
        client.ts
      types/
        index.ts

  eval/
    advisor_questions_v1.jsonl
    expected_evidence_v1.jsonl
    results/

  infra/
    prometheus/
      prometheus.yml
    grafana/
      dashboards/
    k8s/
      backend-deployment.yaml
      frontend-deployment.yaml
      vllm-deployment.yaml
      postgres-statefulset.yaml
      ingress.yaml

  docs/
    architecture.md
    data_schema.md
    rag_design.md
    tool_calling_design.md
    evaluation_plan.md
    benchmark_report.md
    demo_script.md
```

---

## 6. Database Schema

### 6.1 Courses table

```sql
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    course_id TEXT UNIQUE NOT NULL,
    department TEXT NOT NULL,
    course_number TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    credit_hours TEXT,
    prerequisites TEXT,
    source_url TEXT,
    career_tags TEXT[],
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 6.2 Instructors table

```sql
CREATE TABLE instructors (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
```

### 6.3 GPA stats table

```sql
CREATE TABLE gpa_stats (
    id SERIAL PRIMARY KEY,
    course_id TEXT NOT NULL,
    instructor_name TEXT,
    term TEXT,
    average_gpa FLOAT,
    grade_distribution JSONB,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 6.4 Course document chunks

```sql
CREATE TABLE course_chunks (
    id SERIAL PRIMARY KEY,
    course_id TEXT,
    source_name TEXT NOT NULL,
    source_url TEXT,
    section_type TEXT,
    chunk_text TEXT NOT NULL,
    metadata JSONB,
    embedding VECTOR,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 6.5 Evaluation logs

```sql
CREATE TABLE eval_runs (
    id SERIAL PRIMARY KEY,
    run_name TEXT NOT NULL,
    model_name TEXT,
    retriever_config JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

```sql
CREATE TABLE eval_results (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES eval_runs(id),
    question TEXT NOT NULL,
    answer TEXT,
    expected_evidence JSONB,
    retrieved_chunks JSONB,
    latency_ms INTEGER,
    correctness_score FLOAT,
    citation_score FLOAT,
    notes TEXT
);
```

---

## 7. RAG Pipeline Design

### 7.1 Chunking strategy

Use hybrid chunking:

```text
section-based chunking + token chunking
```

Examples:

For each course, create chunks like:

```text
course_description
prerequisites
course_notes
hkn_summary
student_workload_notes
gpa_summary
```

If a section is too long, split by token length.

### 7.2 Retrieval strategy

Version 1:

```text
metadata filter + vector search
```

Version 2:

```text
metadata filter + vector search + keyword search + reranker
```

### 7.3 Retrieval inputs

The retriever should accept:

```json
{
  "query": "Compare ECE 408 and CS 433 for AI infra",
  "course_ids": ["ECE 408", "CS 433"],
  "department_filter": ["ECE", "CS"],
  "top_k": 8
}
```

### 7.4 Retrieval output

The retriever should return:

```json
{
  "chunks": [
    {
      "course_id": "ECE 408",
      "source_name": "UIUC Course Catalog",
      "source_url": "...",
      "section_type": "description",
      "chunk_text": "...",
      "score": 0.82
    }
  ]
}
```

### 7.5 Citation rule

Every factual answer should include evidence.

Citation should include:

```text
source_name
source_url
short snippet
course_id if available
```

### 7.6 RAG fallback rule

If retrieval confidence is low:

```text
1. Try structured DB fallback.
2. If still not enough evidence, answer with uncertainty.
3. Do not hallucinate official requirements.
```

Example safe response:

```text
I could not find enough evidence in the indexed course catalog/wiki data to confirm this. Based on the structured course table, I can only say...
```

---

## 8. Tool Calling Design

### 8.1 Tool router strategy

Version 1:

* implement manual tool router.
* do not depend on LangChain.
* keep tool input/output schemas explicit.

Version 2:

* support OpenAI-compatible function calling style.

### 8.2 Tool list

Implement 6–8 tools.

#### Tool 1: `search_course_docs`

Purpose:

Retrieve relevant course chunks.

Input:

```json
{
  "query": "What is ECE 391 about?",
  "course_ids": ["ECE 391"],
  "top_k": 5
}
```

Output:

```json
{
  "chunks": []
}
```

---

#### Tool 2: `get_course_profile`

Purpose:

Return structured course information.

Input:

```json
{
  "course_id": "ECE 391"
}
```

Output:

```json
{
  "course_id": "ECE 391",
  "title": "...",
  "description": "...",
  "credit_hours": "...",
  "prerequisites": "...",
  "career_tags": ["systems"]
}
```

---

#### Tool 3: `get_gpa_stats`

Purpose:

Return GPA and instructor stats.

Input:

```json
{
  "course_id": "ECE 391",
  "instructor_name": null
}
```

Output:

```json
{
  "course_id": "ECE 391",
  "average_gpa": 3.2,
  "instructor_stats": []
}
```

---

#### Tool 4: `check_prerequisites`

Purpose:

Check whether a student is likely ready for a course.

Input:

```json
{
  "target_course": "ECE 408",
  "completed_courses": ["ECE 385", "ECE 391"]
}
```

Output:

```json
{
  "target_course": "ECE 408",
  "completed_courses": [],
  "missing_prerequisites": [],
  "readiness": "likely_ready",
  "notes": []
}
```

---

#### Tool 5: `compare_courses`

Purpose:

Compare two or more courses using structured info and retrieved evidence.

Input:

```json
{
  "course_ids": ["ECE 408", "CS 433"],
  "dimension": "ai_infra"
}
```

Output:

```json
{
  "courses": [],
  "comparison": {
    "direction_match": {},
    "prereq_level": {},
    "gpa_risk": {},
    "notes": []
  }
}
```

---

#### Tool 6: `recommend_courses`

Purpose:

Recommend courses based on a target direction, with optional completed courses.

Input:

```json
{
  "target_direction": "ai_infra",
  "completed_courses": [],
  "max_results": 5
}
```

Output:

```json
{
  "recommendations": [
    {
      "course_id": "ECE 408",
      "score": 0.86,
      "score_breakdown": {
        "direction_match": 0.4,
        "prerequisite_readiness": 0.2,
        "gpa_risk": 0.1,
        "course_level_progression": 0.16
      },
      "reason_codes": ["gpu_programming", "ai_infra_match"]
    }
  ]
}
```

The score should not be shown to normal users by default.
It should be visible in debug mode and useful for resume/interview explanation.

---

## 9. Query Routing Logic

### 9.1 Simple query path

For simple course QA:

```text
User query
-> detect course_id
-> get_course_profile
-> search_course_docs
-> LLM answer with citations
```

### 9.2 Course comparison path

```text
User query
-> detect multiple course_ids
-> get_course_profile for each
-> get_gpa_stats for each
-> search_course_docs for each
-> compare_courses
-> LLM final answer
```

### 9.3 Recommendation path

First-time user should not be forced to fill a long profile.

Flow:

```text
User: I want AI infra. What should I take?

System:
1. target_direction = ai_infra
2. completed_courses = optional empty list
3. recommend_courses(target_direction)
4. answer with ranked suggestions
5. ask optional follow-up:
   "If you tell me your completed courses, I can refine the recommendation."
```

### 9.4 Complex query path

For complex queries, use LLM planner later.

Version 1 can use rule-based intent detection.

Version 2 should support:

```text
intent = course_qa | comparison | recommendation | prereq_check | gpa_analysis
```

---

## 10. Recommendation Design

### 10.1 Version 1 recommendation input

Required:

```text
target_direction
```

Optional:

```text
completed_courses
preferred_difficulty
semester_plan
```

Do not force user profile in first interaction.

### 10.2 Score components

Use:

```text
direction_match
prerequisite_readiness
gpa_grading_risk
course_level_progression
```

Do not use workload preference in v1.

### 10.3 Example scoring formula

This is only a starting point.

```python
score = (
    0.40 * direction_match
    + 0.25 * prerequisite_readiness
    + 0.20 * course_level_progression
    + 0.15 * gpa_risk_score
)
```

### 10.4 Score display rule

Normal UI:

* no numeric score.

Debug mode:

* show score and score breakdown.

README/resume:

* mention structured scoring and evidence-grounded explanation.

---

## 11. API Design

### 11.1 Health check

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

---

### 11.2 Chat endpoint

```http
POST /api/chat
```

Request:

```json
{
  "message": "Compare ECE 408 and CS 433 for AI infra",
  "conversation_id": "optional",
  "debug": false
}
```

Response:

```json
{
  "answer": "...",
  "citations": [
    {
      "source_name": "UIUC Course Catalog",
      "source_url": "...",
      "course_id": "ECE 408",
      "snippet": "..."
    }
  ],
  "used_tools": [
    "get_course_profile",
    "search_course_docs",
    "compare_courses"
  ],
  "debug_trace": null,
  "latency_ms": 1234
}
```

If `debug=true`, include:

```json
{
  "debug_trace": {
    "intent": "comparison",
    "tool_calls": [],
    "retrieved_chunks": [],
    "recommendation_scores": []
  }
}
```

---

### 11.3 Course compare endpoint

```http
POST /api/compare
```

Request:

```json
{
  "course_ids": ["ECE 408", "CS 433"],
  "dimension": "ai_infra",
  "debug": false
}
```

Response:

```json
{
  "summary": "...",
  "courses": [],
  "comparison": {},
  "citations": []
}
```

---

### 11.4 Recommendation endpoint

```http
POST /api/recommend
```

Request:

```json
{
  "target_direction": "ai_infra",
  "completed_courses": [],
  "max_results": 5,
  "debug": false
}
```

Response:

```json
{
  "recommendations": [
    {
      "course_id": "ECE 408",
      "title": "...",
      "reason": "...",
      "citations": []
    }
  ],
  "debug_scores": null
}
```

---

## 12. Frontend SOP

### 12.1 Version 1 pages

Implement first:

```text
ChatPage
ComparePage
```

### 12.2 Version 2 pages

Implement later:

```text
UserProfileForm
CitationPanel
DebugToolTracePanel
```

### 12.3 Chat page requirements

Chat page should include:

* input box,
* streaming or normal answer display,
* citation list,
* optional debug toggle,
* suggested example prompts.

Example prompts:

```text
What is ECE 391 about?
Compare ECE 408 and CS 433 for AI infra.
What courses are useful for ML systems?
Is ECE 385 useful before ECE 391?
What should I take if I want systems and AI infra?
```

### 12.4 Compare page requirements

Compare page should include:

* course A input,
* course B input,
* optional comparison dimension,
* result cards for each course,
* recommendation summary,
* citations.

---

## 13. vLLM Serving SOP

### 13.1 Development modes

Support three modes:

```text
1. VLLM_REMOTE
2. MOCK_OPENAI_COMPATIBLE
3. EXTERNAL_API_DEBUG
```

Use env var:

```bash
LLM_BACKEND=vllm_remote
```

Possible values:

```bash
vllm_remote
mock
external_debug
```

### 13.2 LLM client interface

Create one unified client:

```python
class LLMClient:
    async def generate(self, messages, temperature=0.2, stream=False):
        pass
```

All backend logic should call this client.
Do not call provider SDKs directly inside route handlers.

### 13.3 vLLM endpoint contract

Assume OpenAI-compatible API:

```text
POST /v1/chat/completions
```

Environment variables:

```bash
VLLM_BASE_URL=
VLLM_API_KEY=
MODEL_NAME=
```

### 13.4 Streaming

Version 1:

* normal response is acceptable.

Version 2:

* add streaming response.

---

## 14. Observability SOP

### 14.1 Metrics to collect

Collect:

```text
request_count
request_latency_ms
retrieval_latency_ms
tool_latency_ms
llm_latency_ms
total_latency_ms
tokens_in
tokens_out
tokens_per_second
error_count
citation_count
tool_success_rate
```

Version 3 adds GPU/vLLM metrics if available:

```text
gpu_utilization
gpu_memory_used
batch_size
kv_cache_usage
```

### 14.2 Logging

Every chat request should log:

```json
{
  "request_id": "...",
  "intent": "comparison",
  "used_tools": [],
  "retrieval_latency_ms": 0,
  "llm_latency_ms": 0,
  "total_latency_ms": 0,
  "error": null
}
```

### 14.3 Grafana dashboard

Create dashboard sections:

```text
API latency
LLM latency
retrieval latency
error rate
tokens/sec
requests/sec
tool success rate
```

---

## 15. Evaluation SOP

### 15.1 Purpose

Evaluation dataset is used to prove the system works.

Without evaluation, the project is only:

```text
I think the chatbot works.
```

With evaluation, the project becomes:

```text
I measured answer correctness, citation correctness, retrieval quality, and serving latency across different RAG/serving configurations.
```

### 15.2 Version 1 evaluation dataset

Use:

```text
30–50 advisor-style questions
```

Build it with:

```text
A. manually write 20 high-quality questions
B. use LLM to generate more candidate questions
C. manually review and keep 30–50 final questions
```

### 15.3 Question categories

Use four categories:

```text
course_qa
course_comparison
gpa_instructor_evidence
direction_recommendation
```

### 15.4 Example JSONL format

File:

```text
eval/advisor_questions_v1.jsonl
```

Example:

```json
{"id":"q001","category":"course_qa","question":"What is ECE 391 about?","expected_evidence":["Should mention systems programming or low-level programming.","Should cite catalog or course wiki."]}
{"id":"q002","category":"course_comparison","question":"Compare ECE 408 and CS 433 for AI infrastructure.","expected_evidence":["ECE 408 should be connected to GPU or parallel programming if supported by data.","CS 433 should be connected to computer organization or architecture if supported by data.","Should not claim one is objectively easier without evidence."]}
{"id":"q003","category":"direction_recommendation","question":"What courses are useful if I want to learn AI infrastructure?","expected_evidence":["Should recommend courses with ai_infra/systems tags.","Should ask for completed courses as optional follow-up."]}
```

### 15.5 First version metrics

Version 1 metrics:

```text
answer_correctness
citation_correctness
latency
```

Later metrics:

```text
retrieval_recall
tool_success_rate
reranker_improvement
p95_latency
p99_latency
```

---

## 16. Load Testing SOP

### 16.1 Version 1 load test

Goal:

```text
10–20 concurrent users
```

Measure:

```text
p50 latency
p95 latency
p99 latency
requests/sec
error rate
tokens/sec
```

### 16.2 Later stretch

Goal:

```text
100+ concurrent users
```

This is for learning high-concurrency serving.

Do not attempt 100+ users before Version 1 and Version 2 are stable.

### 16.3 Suggested tools

Use one of:

```text
locust
k6
hey
wrk
```

Prefer `locust` if Python integration is easier.

---

## 17. Kubernetes SOP

Do not start Kubernetes before the app works locally.

### 17.1 K8s features to implement later

Implement:

```text
Deployment
Service
Ingress
ConfigMap
Secret
readinessProbe
livenessProbe
rolling update
HPA
```

### 17.2 Services

K8s components:

```text
frontend
backend
postgres
vllm-server
prometheus
grafana
```

### 17.3 Failure injection later

Failure scenarios:

```text
1. Kill backend pod.
2. Kill vLLM pod.
3. Make vector DB temporarily unavailable.
4. Add artificial LLM timeout.
5. Test fallback behavior.
```

Measure:

```text
time_to_recover
failed_requests
p95_latency_during_failure
whether fallback worked
```

---

## 18. 12-Week Execution Plan

## Weeks 1–4: Working MVP

### Week 1: Repo + backend skeleton + database

Tasks:

* [ ] Create repository structure.
* [ ] Create FastAPI backend.
* [ ] Add `/health`.
* [ ] Add PostgreSQL Docker Compose.
* [ ] Add pgvector extension.
* [ ] Implement database models:

  * [ ] courses
  * [ ] instructors
  * [ ] gpa_stats
  * [ ] course_chunks
* [ ] Add `.env.example`.
* [ ] Add basic tests.

Definition of done:

* Backend starts locally.
* PostgreSQL starts from Docker Compose.
* `/health` returns ok.
* Database migrations work.

---

### Week 2: Data ingestion

Tasks:

* [ ] Implement `ingest_catalog.py`.
* [ ] Implement `ingest_hkn.py`.
* [ ] Implement `ingest_gpa.py`.
* [ ] Implement `ingest_prereqs.py`.
* [ ] Normalize course IDs.
* [ ] Store source URLs.
* [ ] Build initial 30–50 ECE/CS core course dataset.
* [ ] Manually label career tags for core courses.

Definition of done:

* Database contains 30–50 courses.
* Each course has source URL.
* At least some courses have GPA stats.
* At least some courses have prerequisite data.
* Career tags exist for key courses.

---

### Week 3: RAG pipeline

Tasks:

* [ ] Implement chunker.
* [ ] Implement embedder.
* [ ] Store embeddings in pgvector.
* [ ] Implement retriever.
* [ ] Add metadata filters.
* [ ] Implement citation formatter.
* [ ] Add `/api/chat` with simple RAG.

Definition of done:

* User can ask course questions.
* System retrieves relevant chunks.
* Answer includes citations.
* RAG fallback works when no evidence is found.

---

### Week 4: Frontend MVP

Tasks:

* [ ] Create React frontend.
* [ ] Implement ChatPage.
* [ ] Implement ComparePage.
* [ ] Implement API client.
* [ ] Display answer.
* [ ] Display citations.
* [ ] Add example prompts.

Definition of done:

* User can use web UI.
* Chat works.
* Course comparison works at basic level.
* Demo is possible.

---

## Weeks 5–8: Tool Calling + Serving Metrics

### Week 5: Tool router

Tasks:

* [ ] Implement tool schemas.
* [ ] Implement manual router.
* [ ] Implement:

  * [ ] `search_course_docs`
  * [ ] `get_course_profile`
  * [ ] `get_gpa_stats`
  * [ ] `check_prerequisites`
  * [ ] `compare_courses`
  * [ ] `recommend_courses`
* [ ] Add debug trace object.

Definition of done:

* Backend can route simple vs complex queries.
* Tools return structured JSON.
* Debug mode shows used tools.

---

### Week 6: Recommendation system

Tasks:

* [ ] Implement direction-based recommendation.
* [ ] Add score components:

  * [ ] direction_match
  * [ ] prerequisite_readiness
  * [ ] gpa_risk
  * [ ] course_level_progression
* [ ] Hide score in normal UI.
* [ ] Show score in debug mode.
* [ ] Add `/api/recommend`.

Definition of done:

* User can ask: “What courses are good for AI infra?”
* System gives course recommendations without requiring profile.
* System optionally asks for completed courses as follow-up.

---

### Week 7: vLLM integration

Tasks:

* [ ] Implement unified `LLMClient`.
* [ ] Add support for:

  * [ ] vLLM remote endpoint
  * [ ] mock endpoint
  * [ ] external debug endpoint
* [ ] Add env configuration.
* [ ] Add streaming if feasible.
* [ ] Test on Colab GPU or school GPU.

Definition of done:

* Backend can call vLLM-compatible endpoint.
* External API is only a debug fallback.
* README explains self-hosted serving path.

---

### Week 8: Metrics + evaluation v1

Tasks:

* [ ] Add request latency metrics.
* [ ] Add retrieval latency metrics.
* [ ] Add LLM latency metrics.
* [ ] Add tool success metrics.
* [ ] Build `eval/advisor_questions_v1.jsonl`.
* [ ] Implement `eval_runner.py`.
* [ ] Run first evaluation.

Definition of done:

* Evaluation dataset has 30–50 questions.
* Report includes correctness/citation/latency.
* Metrics are visible locally.

---

## Weeks 9–12: Infra Depth + Benchmark

### Week 9: Prometheus + Grafana

Tasks:

* [ ] Add Prometheus config.
* [ ] Add Grafana dashboard.
* [ ] Export backend metrics.
* [ ] Add dashboard screenshots to docs.

Definition of done:

* Grafana shows latency, error rate, tool success, requests/sec.

---

### Week 10: Load testing

Tasks:

* [ ] Add Locust or k6 load test.
* [ ] Test 10–20 concurrent users.
* [ ] Measure p50/p95/p99 latency.
* [ ] Record results.
* [ ] Try improving bottlenecks.

Definition of done:

* Benchmark report has first load test result.
* Bottlenecks are identified.

---

### Week 11: Kubernetes deployment

Tasks:

* [ ] Add K8s manifests.
* [ ] Deploy backend.
* [ ] Deploy frontend.
* [ ] Deploy PostgreSQL or connect to external DB.
* [ ] Add readiness/liveness probes.
* [ ] Add rolling update config.

Definition of done:

* App can run in Kubernetes.
* Basic rollout works.

---

### Week 12: Reliability stretch + final report

Tasks:

* [ ] Kill backend pod and measure recovery.
* [ ] Simulate vLLM timeout.
* [ ] Simulate DB retrieval failure.
* [ ] Add fallback behavior.
* [ ] Write final benchmark report.
* [ ] Write final README.
* [ ] Prepare demo script.
* [ ] Prepare resume bullets.

Definition of done:

* Final demo works.
* README is polished.
* Benchmark report exists.
* Reliability experiment exists, even if simple.

---

## 19. README Structure

Final README should include:

```text
1. Project Overview
2. Why this is not just a chatbot
3. Architecture Diagram
4. Tech Stack
5. Features
6. Data Sources
7. RAG Pipeline
8. Tool Calling Design
9. vLLM Serving Setup
10. Observability
11. Evaluation
12. Load Testing
13. Kubernetes Deployment
14. Failure Injection Experiments
15. Demo
16. Lessons Learned
```

---

## 20. Demo Script

Use this order in demo:

### Demo 1: Course QA

Prompt:

```text
What is ECE 391 about?
```

Show:

* answer,
* citations,
* retrieved evidence.

---

### Demo 2: Course Comparison

Prompt:

```text
Compare ECE 408 and CS 433 for AI infrastructure.
```

Show:

* structured comparison,
* citations,
* tool trace in debug mode.

---

### Demo 3: Recommendation

Prompt:

```text
I want to learn AI infrastructure. What courses should I take?
```

Show:

* no required user profile,
* recommendation result,
* optional follow-up asking for completed courses.

---

### Demo 4: Observability

Show Grafana:

* p95 latency,
* request count,
* LLM latency,
* retrieval latency,
* tool success rate.

---

### Demo 5: Benchmark

Show:

* 10–20 concurrent user test,
* p50/p95/p99 latency,
* error rate,
* bottleneck analysis.

---

## 21. Resume Bullets Draft

Use after project is implemented.

### AI Infra version

```text
Built IlliniGuide Serve, a self-hosted LLM/RAG serving platform for UIUC ECE/CS advising workloads using FastAPI, React, vLLM, PostgreSQL/pgvector, and Prometheus/Grafana.
```

```text
Implemented a hybrid RAG pipeline combining metadata-filtered vector search, structured course/GPA tools, citation grounding, and advisor-style LLM responses.
```

```text
Designed tool orchestration for course QA, course comparison, GPA lookup, prerequisite checking, and direction-based course recommendation, separating LLM reasoning from deterministic structured computation.
```

```text
Benchmarked LLM serving performance under concurrent academic advising queries, tracking p50/p95/p99 latency, retrieval latency, generation latency, token throughput, and error rate.
```

### Stronger later version

```text
Deployed the platform on Kubernetes with readiness probes, rolling updates, autoscaling experiments, and failure-injection tests for vLLM/backend/vector DB recovery.
```

---

## 22. Codex Implementation Instructions

When using Codex, follow this order.

### Phase 1: Do not overbuild

Start with:

```text
backend skeleton
database schema
basic ingestion
basic RAG
chat API
frontend chat page
```

Do not start with:

```text
Kubernetes
failure injection
large-scale benchmark
complex auth
fine-tuning
```

### Phase 2: Keep interfaces clean

Important rule:

```text
Route handlers should not directly implement business logic.
```

Use this separation:

```text
api/ = HTTP routes
services/rag/ = retrieval and citations
services/tools/ = structured tools
services/llm/ = LLM client
ingestion/ = data pipelines
evaluation/ = eval runner
```

### Phase 3: Always add acceptance tests

For each major feature, add tests.

Examples:

```text
test course_id normalization
test retriever returns citations
test get_course_profile
test compare_courses
test recommend_courses
test chat endpoint returns answer + citations
```

### Phase 4: Every feature should be demoable

For every new feature, update:

```text
README
docs/demo_script.md
sample prompts
```

---

## 23. Immediate First Tasks for Codex

Start here.

### Task 1: Initialize repository

Create:

```text
backend/
frontend/
docs/
eval/
infra/
```

Add:

```text
README.md
PROJECT_SOP.md
.env.example
docker-compose.yml
```

---

### Task 2: Implement backend skeleton

Create FastAPI app with:

```text
GET /health
POST /api/chat
POST /api/compare
POST /api/recommend
```

For now, return mocked responses.

---

### Task 3: Implement database models

Create models for:

```text
courses
instructors
gpa_stats
course_chunks
eval_runs
eval_results
```

---

### Task 4: Implement mock RAG

Before embeddings are ready, implement a simple keyword-based retriever over sample course data.

Use this to unblock frontend.

---

### Task 5: Implement frontend MVP

Create:

```text
ChatPage
ComparePage
CitationList
ToolTracePanel
```

Make the frontend work with mocked backend first.

---

## 24. Definition of Final Success

This project is successful if it can demonstrate:

```text
1. A user can ask UIUC ECE/CS course advising questions.
2. The system answers with citations.
3. The system can compare courses.
4. The system can recommend courses for a career direction without requiring a long profile.
5. The backend uses structured tools, not only raw LLM prompting.
6. The LLM endpoint can be self-hosted through vLLM.
7. The system records latency and tool metrics.
8. The project includes an evaluation dataset.
9. The project includes a benchmark report.
10. Later version includes Kubernetes and basic reliability experiments.
```

---

## 25. Key Interview Framing

Do not say:

```text
I built a course chatbot.
```

Say:

```text
I built a self-hosted LLM/RAG serving platform for academic advising workloads. The main focus was not only answer generation, but building a reliable serving pipeline with vLLM, structured tool orchestration, vector retrieval, citation grounding, observability, and benchmark evaluation.
```

Do not say:

```text
The LLM recommends courses.
```

Say:

```text
The LLM acts as a planner and explanation layer. Course facts, GPA statistics, prerequisite checks, and recommendation scores are computed by structured tools, and the final response is grounded with citations.
```

Do not say:

```text
I used RAG.
```

Say:

```text
I built a hybrid retrieval pipeline using course metadata filters, pgvector embeddings, structured course tables, and citation-aware response generation.
```
