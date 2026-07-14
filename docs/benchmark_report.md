# Benchmark Report

## Retrieval evaluation results

**Status: Partial — local Docker/PostgreSQL baseline recorded; not an
ICRN/H200 benchmark.** The result measures retrieval evidence only, not answer
quality or relevance.

| Run | Corpus / embedding | Evidence Recall@3 | Unfiltered Recall@3 | Source correctness | Section correctness | Unsupported safety |
|---|---|---:|---:|---:|---:|---:|
| Semantic pgvector, listing-only baseline | 360 source-tagged courses; 268 MiniLM 384-d chunks | 14/30 (46.7%) | 8/22 (36.4%) | 9/30 (30.0%) | 6/16 (37.5%) | 1/4 (25.0%) |
| Semantic pgvector, enriched official catalog | 367 source-tagged courses; 1,045 MiniLM 384-d chunks | 17/30 (56.7%) | 9/22 (40.9%) | 13/30 (43.3%) | 7/16 (43.8%) | 1/4 (25.0%) |
| Keyword chunk baseline, enriched official catalog | Same enriched corpus / frozen cases | 17/30 (56.7%) | 9/22 (40.9%) | 15/30 (50.0%) | 4/16 (25.0%) | 0/4 (0.0%) |

The raw local artifacts are intentionally uncommitted but available in the
working tree under `artifacts/retrieval_eval/20260713T084605Z-8b98e35/` and
`artifacts/retrieval_eval/20260713T084635Z-8b98e35/`. They use
`retrieval_cases.v1`, top-k 3, and
`sentence-transformers/all-MiniLM-L6-v2`. The enriched semantic and keyword
artifacts are `20260713T094627Z-973add9` and `20260713T094651Z-973add9`.

These results **forbid** a “92% answer relevance” claim. The current failure
pattern was improved by official-description enrichment: only 1 of 367 courses
now produced no chunk, and semantic unfiltered Recall@3 rose 4.5 percentage
points. The remaining problem is direct course-ID routing and explicit
unsupported-query handling, followed by another frozen-case evaluation.
