# Retrieval Evaluation Plan

**Status: Partial — harness implemented and a local Docker/PostgreSQL baseline
has been recorded; result improvement is pending.**

This plan evaluates whether the retriever returned appropriate catalog evidence
before any LLM answer is generated. It does not measure advice quality,
helpfulness, or generated-answer correctness.

## Frozen input

The versioned label file is
[`backend/evaluation/retrieval_cases.v1.json`](../backend/evaluation/retrieval_cases.v1.json).
It contains 34 advisor-style cases covering direct course lookup, prerequisite
section lookup, paraphrases, cross-course discovery, metadata-sensitive
queries, and unsupported questions. Each supported query labels acceptable
course IDs and, where the evidence type matters, the expected chunk section
and source name. Unsupported queries label the acceptable safe outcome:
`no_evidence` or `low_confidence_or_no_evidence`.

The case file is frozen for a run: change it only by creating a new versioned
file such as `retrieval_cases.v2.json`, not by editing labels after observing a
result.

## Rubric

| Metric | Denominator | Correct when |
|---|---:|---|
| Recall@1 | supported cases | top retrieved chunk has an acceptable course ID |
| Recall@k | supported cases | any of the top-k chunks has an acceptable course ID |
| Unfiltered Recall@k | supported non-`metadata_filtered` cases | any top-k chunk has an acceptable course ID without a harness-supplied course-ID filter |
| Source/citation correctness | cases with source label | top chunk has both an acceptable course ID and the expected source name |
| Section correctness | cases with section label | top chunk has both an acceptable course ID and expected `section_type` |
| Unsupported-query safety correctness | unsupported cases | no evidence is returned, or top similarity is below the documented low-confidence threshold; invented-course cases require no evidence |

`source/citation correctness` checks the retrieved citation metadata, not
whether an LLM rendered a citation in prose. The low-confidence threshold is
the current retriever's `LOW_CONFIDENCE_THRESHOLD` (0.35). It is a retrieval
safety signal, not a calibrated probability of answer correctness.

## Semantic versus keyword comparison

Run the exact same frozen case file, top-k, and approved corpus twice: once
with `--mode semantic`, once with `--mode keyword`. The harness uses explicit
retriever adapters, so unit tests can stub either path without PostgreSQL. Do
not compare runs with different case versions, corpus snapshots, embedding
models, or top-k values.

Cases labelled `metadata_filtered` derive course IDs from their query and pass
that list to both adapters' `course_ids` argument. The applied list is written
to each raw per-query result. Other categories deliberately do not receive a
filter, preserving a fair test of paraphrase and cross-course discovery. The
aggregate therefore reports both all-supported Recall and **unfiltered Recall**;
use the latter for a headline semantic-retrieval quality claim because the
filtered cases deliberately test metadata-filter behavior, not course discovery.

The keyword baseline ranks the same persisted `course_chunks` corpus as
pgvector retrieval, preserving source and section metadata. Its lexical-overlap
score is not calibrated to cosine similarity, so low-confidence safety is a
semantic-retrieval metric; keyword safety results should be read only as
`no_evidence` behavior, not compared by threshold.

## Live execution gate

Run only after the coordinator has approved the corpus manifest and real MiniLM
embedding ingestion. From `backend/`:

```bash
.venv/bin/python -m pip install -e '.[embeddings]'
```

`sentence-transformers` is intentionally an optional dependency: the mock
embedding backend keeps normal unit tests lightweight, while this extra is
required for a real MiniLM evidence run.

```bash
EMBEDDING_BACKEND=sentence_transformer \
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \
python -m scripts.eval_retrieval --mode semantic --top-k 3 \
  --ingestion-manifest artifacts/ingestion/<approved-run-id>/manifest.json

EMBEDDING_BACKEND=sentence_transformer \
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \
python -m scripts.eval_retrieval --mode keyword --top-k 3 \
  --ingestion-manifest artifacts/ingestion/<approved-run-id>/manifest.json
```

Each command requires the approved combined ingestion manifest, verifies that
its course count/source URLs match the active DB corpus, and creates
`artifacts/retrieval_eval/<run-id>/` with raw per-query results, aggregate
rates, and a manifest. `sentence_transformer` is required by default; the
development-only `--allow-unlinked-corpus` or a different `--require-backend`
setting must never support a resume claim. Review these artifacts before adding
any percentage to a report or resume. The current local baseline is recorded
in `docs/benchmark_report.md`; it is retrieval evidence only and does not
support an answer-relevance claim. No live ICRN evaluation has been run.

## What to inspect before publishing a result

- Verify `case_set.id`, `corpus.distinct_course_count`, `corpus.source_urls`,
  optional `ingestion_manifest` checksum/link, embedding model, mode,
  metadata-filter policy, and top-k in the manifest.
- Review every unsupported case with returned chunks; a high-confidence,
  unrelated chunk is a failure even if supported-case Recall looks strong.
- Inspect source and section misses separately from Recall misses. A course ID
  can be right while its citation source or chunk section is wrong.
- Report numerator/denominator and metric name, for example: “evidence
  Recall@3 on `retrieval_cases.v1`,” never the vague phrase “answer relevance.”

## Interview explanation

> “I froze retrieval labels before running the model and separated evidence
> Recall, citation metadata correctness, section correctness, and unsupported
> query safety. That prevents a strong course-ID Recall number from hiding a
> wrong source or overconfident out-of-scope retrieval.”
