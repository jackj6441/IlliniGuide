# RAG Design

Status: Partial

The current RAG implementation is a Phase 1 DB-aware mock. It is intentionally simple and exists to unblock the API and future frontend before embeddings are ready.

## Implemented

- Sample course chunks for a small set of ECE/CS courses.
- Course ID normalization, such as `ece391` -> `ECE 391`.
- Course ID extraction from user queries.
- Keyword-overlap retrieval over sample chunks.
- Keyword-overlap retrieval over `courses` database rows.
- Fallback from database retrieval to sample chunks.
- Citation formatting from retrieved chunks.
- `/api/chat` and `/api/compare` now use DB-backed keyword retrieval when a database session is available.

## Planned

- Real ingestion from UIUC catalog/HKN/GPA sources.
- Section-based chunking.
- Configurable embeddings.
- pgvector storage and vector search.
- Metadata filtering by `course_id` and department.
- Structured DB fallback.
- Reranking.

## Current Retrieval Flow

```text
user query
-> extract course IDs
-> query matching course rows from PostgreSQL
-> build course profile chunks from title/prerequisites/source URL
-> score chunks by keyword overlap
-> fall back to sample chunks if no DB evidence is found
-> return top-k chunks
-> format citations
-> template-based mock answer
```

## Why This Is Mocked

This is not real semantic retrieval yet. It is a small local substitute for pgvector retrieval so the project can exercise the same API shape early while already using ingested structured course data.

The important contract is:

```text
query -> retrieved evidence -> citations -> grounded answer
```

Later, only the retriever implementation should change. The API response shape should stay stable.
