# Benchmark Report

## Retrieval evaluation results

**Status: Partial — local Docker/PostgreSQL baseline recorded; not an
ICRN/H200 benchmark.** The result measures retrieval evidence only, not answer
quality or relevance.

| Run | Corpus / embedding | Evidence Recall@3 | Unfiltered Recall@3 | Source correctness | Section correctness | Unsupported safety |
|---|---|---:|---:|---:|---:|---:|
| Semantic pgvector | 360 source-tagged courses; 268 MiniLM 384-d chunks | 14/30 (46.7%) | 8/22 (36.4%) | 9/30 (30.0%) | 6/16 (37.5%) | 1/4 (25.0%) |
| Keyword chunk baseline | Same corpus / frozen cases | 17/30 (56.7%) | 11/22 (50.0%) | 14/30 (46.7%) | 6/16 (37.5%) | 0/4 (0.0%) |

The raw local artifacts are intentionally uncommitted but available in the
working tree under `artifacts/retrieval_eval/20260713T084605Z-8b98e35/` and
`artifacts/retrieval_eval/20260713T084635Z-8b98e35/`. They use
`retrieval_cases.v1`, top-k 3, and
`sentence-transformers/all-MiniLM-L6-v2`.

These results **forbid** a “92% answer relevance” claim. The current failure
pattern is expected from catalog rows that provide title/prerequisite text but
lack broad descriptions and career-direction content; 92 of 360 courses
produced no chunk. The next improvement is source enrichment and explicit
unsupported-query handling, followed by a fresh frozen-case evaluation.
