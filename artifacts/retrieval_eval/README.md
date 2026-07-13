# Retrieval evaluation artifacts

Each live execution of `python -m scripts.eval_retrieval` writes one immutable
subdirectory here, named `<UTC timestamp>-<short git sha>` unless a reviewer
supplies `--run-id`.

```text
artifacts/retrieval_eval/<run-id>/
├── per_query_results.json
├── aggregate_report.json
└── run_manifest.json
```

`per_query_results.json` is the raw audit trail: query labels, the applied
course-ID metadata filter, returned chunk metadata, scores, and per-case
metric booleans. `aggregate_report.json` holds
only computed counts and rates. `run_manifest.json` records the frozen case
set ID, retriever mode, top-k, embedding configuration, UTC interval, git SHA,
command, and file list.

Artifacts measure retrieval evidence only. They do not establish LLM answer
correctness, 150-course coverage, or a resume relevance percentage by
themselves. Do not overwrite a run directory; the CLI rejects an existing ID.
