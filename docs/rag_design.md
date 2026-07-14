# RAG Design

Status: Partial — semantic retrieval, scope safety, and a reproducible local
quality report are implemented; broader corpus coverage and ICRN validation
remain pending.

IlliniGuide uses a handwritten retrieval pipeline rather than making LangChain the core architecture. Structured facts such as prerequisites and GPA are handled by deterministic tools; course descriptions and advising context can be retrieved from cited `course_chunks` evidence.

## Evidence Status

| Capability | Status | Evidence / limitation |
|---|---|---|
| Section-based chunking | Implemented | `services/rag/chunker.py` emits focused overview, prerequisites, credit-hours, career-direction, and optional GPA-context chunks. |
| Embedding abstraction | Implemented | Deterministic mock embeddings support tests; `SentenceTransformerBackend` supports `sentence-transformers/all-MiniLM-L6-v2` with 384-dimensional normalized vectors. The real backend must be selected explicitly through `EMBEDDING_BACKEND=sentence_transformer`. |
| Embedding ingestion | Implemented | `ingestion/embed_chunks.py` chunks course rows, embeds them in batches, and replaces each course's persisted `course_chunks` rows idempotently. |
| pgvector retrieval | Implemented | `services/rag/pgvector_retriever.py` orders by cosine distance, excludes `NULL` vectors, converts distance to a similarity score, and returns top-k evidence. |
| Course metadata filtering | Implemented | Callers may restrict semantic retrieval to normalized `course_id` values. A separate department filter is not implemented. |
| Keyword safety net | Implemented | If semantic retrieval returns no rows, the pipeline falls back to the DB-backed keyword retriever. |
| Low-confidence signaling | Implemented | A top semantic similarity below `0.35` adds an explicit grounding warning. It does not silently promote weak evidence to a correct answer. |
| Citation conversion | Implemented | Retrieved chunks preserve course, source, section, snippet, and score fields for downstream citations. |
| Retrieval tests | Implemented | Unit tests cover chunking, embedding behavior, pgvector query construction, filtering, low-confidence notes, empty semantic fallback, and evaluation scoring without requiring a live database. |
| Live retrieval evaluation | Partial | The frozen 34-case set is evaluated through the production router as 22 RAG evidence cases plus four safety cases. The current local tag-seeded semantic run reports Recall@3 20/22 (90.9%), unfiltered Recall@3 8/10 (80.0%), source correctness 20/22, section correctness 6/8, and safety 4/4. This is not an ICRN/H200 or answer-quality result. |

## Current Retrieval Flow

```text
user query
-> validate query and normalize optional course IDs
-> embed query with the configured EmbeddingClient
-> cosine top-k search over non-null pgvector course_chunks
-> optionally filter by course_id
-> if semantic rows exist:
     return them and add a note when top similarity < 0.35
-> otherwise:
     fall back to DB-backed keyword retrieval
-> convert chunks to RetrievedDoc evidence
-> pass evidence and citations to answer synthesis
```

The API contract remains:

```text
query -> retrieved evidence -> citations -> grounded answer
```

The LLM does not replace retrieval. It receives the selected evidence after the retriever and structured tools have run.

## Why the Overall Status Is Partial

There are three different evidence levels:

1. **Implemented code:** section chunking, MiniLM adapter, pgvector persistence/search, filtering, fallback, and tests exist.
2. **Live execution:** real MiniLM ingestion must be run against the approved PostgreSQL corpus instead of the default mock embedding backend.
3. **Measured quality:** a frozen advisor query set must be run and its per-query and aggregate results saved.

The repository now satisfies the first two levels and has a reproducible local
retrieval report. It still does not support claims such as “92% answer
relevance”: the report measures retrieved evidence, not generated answer
quality, and the corpus is not an ICRN/H200 validation run.

## Next Validation Gate

- Expand the frozen set only through a new versioned case file if broader topic coverage is needed.
- Calibrate topic coverage and any reranker against the current 367-course corpus without weakening the scope guard.
- Repeat the real MiniLM ingestion/evaluation on ICRN before using the result as a deployment benchmark.

Reranking remains Planned. It should be considered only after the basic evaluation identifies a top-k precision problem worth its additional latency and complexity.

## Latency and Quality Tradeoffs

- Query embedding adds model-inference latency before database search. The mock backend is useful for deterministic tests but says nothing about real MiniLM latency or retrieval quality.
- Increasing `top_k` may improve evidence recall, but it also returns more weakly related context and increases prompt length, prefill work, and citation-review cost.
- Course-ID filtering reduces the pgvector search space and prevents semantically similar evidence from unrelated courses from entering the answer. An incorrect filter can instead hide the right chunk.
- Keyword fallback keeps local development useful when no semantic rows are available, but exact term overlap is less robust to paraphrases. Evaluation must report semantic and fallback behavior separately.
- The `0.35` low-confidence threshold is a conservative warning, not a proven optimum. It should be calibrated against the frozen evaluation set before being treated as a quality boundary.
- A reranker may improve top-k precision, but it adds another inference step and therefore increases latency and operational complexity.

## Interview Explanation

> “I separated structured facts from unstructured retrieval. Prerequisites and GPA come from deterministic tools, while course descriptions are split by section, embedded with MiniLM, stored in pgvector, and retrieved with course-aware filters. The implementation is complete at the code level, but I describe retrieval quality as partial until a frozen live evaluation report is published.”

## Review Questions

1. Why use section-based chunks instead of blindly splitting by token count?

   Answer: A prerequisite query should retrieve a focused prerequisite chunk rather than compete with unrelated overview, GPA, and career text from one large document.

2. Why keep the keyword fallback?

   Answer: It preserves useful behavior when vectors have not been ingested or semantic search returns no rows, while still allowing the system to report no evidence when both paths are empty.

3. Does a low similarity score prove that an answer is wrong?

   Answer: No. It is a risk signal. The pipeline surfaces it so answer synthesis can be conservative, and the threshold must be calibrated using labeled evaluation cases.
