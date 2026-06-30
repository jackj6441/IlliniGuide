# Demo Script

Status: Planned

This file will become the demo script as features are implemented. Do not describe a feature as working until it has been implemented and verified.

## Planned Demo Flow

1. Course QA: ask what a course is about and show citations.
2. Course comparison: compare two courses and show structured evidence.
3. Recommendation: recommend courses for a target direction without requiring a long profile.
4. Observability: show latency and tool metrics.
5. Benchmark: show concurrent-user test results.

## Current Demo Status

Status: Partial

The repository skeleton exists. The backend API skeleton is implemented with mocked responses. `/api/chat` uses a keyword-based mock RAG retriever over sample course chunks. Frontend UI, real pgvector RAG, tool routing, vLLM integration, and metrics are not implemented yet.
