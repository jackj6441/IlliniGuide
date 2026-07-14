# Benchmark Report

## Retrieval evaluation results

**Status: Partial — local Docker/PostgreSQL baseline recorded; not an
ICRN/H200 benchmark.** The result measures retrieval evidence only, not answer
quality or relevance.

| Run | Corpus / embedding | Evidence Recall@3 | Non-filtered Recall@3 | Source correctness | Section correctness | Unsupported safety |
|---|---|---:|---:|---:|---:|---:|
| Semantic pgvector, listing-only baseline | 360 source-tagged courses; 268 MiniLM 384-d chunks | 14/30 (46.7%) | 8/22 (36.4%) | 9/30 (30.0%) | 6/16 (37.5%) | 1/4 (25.0%) |
| Semantic pgvector, enriched official catalog | 367 source-tagged courses; 1,045 MiniLM 384-d chunks | 17/30 (56.7%) | 9/22 (40.9%) | 13/30 (43.3%) | 7/16 (43.8%) | 1/4 (25.0%) |
| Keyword chunk baseline, enriched official catalog | Same enriched corpus / frozen cases | 17/30 (56.7%) | 9/22 (40.9%) | 15/30 (50.0%) | 4/16 (25.0%) | 0/4 (0.0%) |
| Semantic pgvector, production-router-aligned + scope guard | Same enriched corpus; 1,045 MiniLM 384-d chunks; 22 RAG evidence cases | 14/22 (63.6%) | 2/10 (20.0%) | 14/22 (63.6%) | 0/8 (0.0%) | 4/4 (100.0%) |
| Keyword chunk baseline, production-router-aligned + scope guard | Same corpus; 22 RAG evidence cases | 15/22 (68.2%) | 3/10 (30.0%) | 14/22 (63.6%) | 0/8 (0.0%) | 4/4 (100.0%) |

The raw local artifacts are intentionally uncommitted but available in the
working tree under `artifacts/retrieval_eval/20260713T084605Z-8b98e35/` and
`artifacts/retrieval_eval/20260713T084635Z-8b98e35/`. They use
`retrieval_cases.v1`, top-k 3, and
`sentence-transformers/all-MiniLM-L6-v2`. The enriched semantic and keyword
artifacts are `20260713T094627Z-973add9` and `20260713T094651Z-973add9`.
The production-router-aligned semantic and keyword artifacts before the scope
guard are `20260714T013614Z-9b2f556` and `20260714T013641Z-9b2f556`. The current
scope-guard runs are `20260714T020534Z-1092e30` and
`20260714T020600Z-1092e30`.

The first three runs use the former policy, which treats all 30 evidence labels
as RAG cases and filters only eight ``metadata_filtered`` cases; their
non-filtered denominator is therefore 22. The production-router-aligned runs
derive eligibility and filters from the actual tool plan. They exclude the
eight prerequisite cases because chat uses the structured
``check_prerequisites`` tool for them, leaving 22 RAG evidence cases and four
safety cases. Their non-filtered denominator is the ten open-discovery cases,
so **40.9% and 20.0% are not directly comparable quality claims**. On the
production RAG path, all 12 direct-ID lookup cases retrieved the requested
course, and invented ``ECE 999`` returned no evidence; this does not solve
open-discovery quality or all out-of-scope questions.

These results **forbid** a “92% answer relevance” claim. Official-description
enrichment reduced empty courses from 92/360 to 1/367, then direct-ID routing
made exact course lookup behavior defensible. The remaining problem is
open-discovery retrieval and section correctness: semantic search is 2/10 on
the unfiltered discovery subset and 0/8 for the expected evidence section. The
scope guard now rejects all four unsupported cases (4/4 safety), but it also
abstains on the GPU paraphrase because the current top-k evidence lacks a
shared topic token. The next improvement should add a reranking/topic-coverage
step to recover valid paraphrases without weakening the safety guard.
