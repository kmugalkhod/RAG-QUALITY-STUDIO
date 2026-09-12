# Development

Local setup and baseline verification commands are documented in [README](../README.md).

## Pipeline kinds

Pipeline collections accept `kind=answer` or `kind=ingestion`; executable answer selectors always request `answer`. Existing create requests without `kind` remain answer pipelines. Phase 1 accepts a strictly validated ingestion configuration through the shared create/version APIs, but the production UI intentionally disables ingestion creation and there is no ingestion preview, run or worker endpoint yet. Do not treat a saved ingestion graph as an index or successful execution.

## Knowledge sets and explicit index snapshots

Every project has a stable **Uploaded documents** knowledge set. `POST /api/projects/{project_id}/indexes` without a body preserves the Knowledge Base workflow by resolving every currently successful document to its latest successful processing run. To snapshot a narrower selection, send `{"document_ids":["<document UUID>"]}`; callers may also specify a project-owned `knowledge_set_id`. The backend converts either request to exact processing-run/chunk membership before queueing. Missing, cross-project, unfinished, duplicate and empty selections are rejected.

Use `GET /api/projects/{project_id}/knowledge-sets` and `GET /api/projects/{project_id}/knowledge-sets/{knowledge_set_id}/indexes` for bounded destination/version listings. Index reads identify their knowledge set, distinct source-run count and current-ready status. “Current” is informational: answer pipelines and experiments continue to execute their saved index UUID and never advance automatically.

## Evaluation experiments

Set server-only `EVALUATOR_MODEL` (independent of `CHAT_MODEL`) and `OPENROUTER_API_KEY`, then recreate backend, worker and dispatcher. Response relevancy reuses the configured OpenRouter embedding model. `EVALUATOR_MAX_TOKENS` defaults to 4096; `DATASET_MAX_ROWS` defaults to 200 and `DATASET_MAX_BYTES` to 2097152. Model calls have no automatic paid retries. Keep the dispatcher running for progress and stale recovery.

In a project, open Experiments, download the example CSV, replace it with reviewed questions for that project's sources, preview, and import. Reference answers are optional; context recall is unavailable for rows without them. Choose one or two saved pipeline versions, select metrics, and run. Open a question in the comparison table to see answers, exact supplied evidence and available structured judge explanations. Export CSV or inspect the immutable snapshot. LLM scores require human review.

The opt-in `backend/scripts/check_experiment_live.py --project <sample-orchard-project> --version <saved-version> [--version <second-version>]` submits exactly three reviewed orchard questions through the running API. Only run against the matching orchard sample source; it creates persistent dataset and experiment records and makes paid calls. It cancels scheduling after a 15-minute deadline. Default automated tests use deterministic provider/evaluator doubles and do not use credentials.

## Retrieval search settings

The Retrieval node, Playground and Knowledge Base search share six controls. Search method and Top k are basic controls; the optional vector-distance cutoff and hybrid candidate counts/weight are under Advanced search settings. Inputs remain separate from search behavior. No filters or reranking were added.

`POST /api/projects/{project_id}/retrieval` accepts:

```json
{
  "index_id": "<ready index UUID>",
  "query": "apples OR harvest",
  "retrieval": {
    "mode": "hybrid",
    "top_k": 5,
    "max_vector_distance": null,
    "vector_candidates": 50,
    "keyword_candidates": 50,
    "vector_weight": 0.5
  }
}
```

Vector mode accepts Top k and the optional distance cutoff. Keyword mode accepts only Top k. Hybrid additionally accepts both candidate counts and vector weight. Top k is 1–50; each candidate count is between Top k and 200; vector weight is 0–1 and keyword weight is its complement. Distances are inclusive 0–2, with null disabling the cutoff. Unknown/inapplicable fields, non-finite numbers, and ambiguous requests containing both legacy `top_k` and nested `retrieval` are rejected. The direct query API accepts the same `retrieval` object alongside `question` and `index_id`; flat Top k remains a dense-search compatibility input.

Keyword search uses PostgreSQL `simple` analysis and `websearch_to_tsquery`: ordinary words are ANDed, quoted phrases and OR are supported. Ranking uses `ts_rank_cd`, not BM25. It is not substring search or universal multilingual stemming. Keyword retrieval needs a previously prepared ready index but no query embedding credentials. Vector search retains exact cosine retrieval using the source index's embedding configuration.

Hybrid merges the two bounded ranked lists by chunk identity with weighted reciprocal rank fusion, using constant 60. The vector cutoff affects only the vector branch; a keyword match can still appear independently. Zero-weight branches are skipped. An active branch failure fails the run, while an empty branch is valid. No final matches returns no evidence rather than broadening scope. No answer-model call is made when no evidence is retrieved.

Evidence reports nullable cosine distance, keyword score, RRF score and branch ranks. Lower cosine distance is closer; higher lexical/RRF scores rank first. None is confidence, and score magnitudes are not comparable across modes. Search responses include effective settings and branch counts/timings. Answer snapshots retain retrieval outputs separately from evidence actually supplied to generation; experiment exports include retrieval settings/results. Settings are snapshotted before deferred work starts.

Migration `0007` creates a GIN expression index over immutable chunk text. It covers existing rows and future inserts without re-embedding. Index construction can block writes to chunks while the migration runs; schedule large upgrades during a maintenance window. Rollback to `0006` drops only the lexical index, preserving chunks, embeddings and historical runs. Backend/frontend code should be rolled back together; an older backend cannot execute schema-v2 pipelines. Existing v1 pipelines remain loadable and executable; editing and saving creates a new v2 version without rewriting history. Search remains bounded to 50,000-chunk source snapshots and has not been benchmarked for larger deployments.

## Frontend maintenance

See [frontend standards](frontend-standards.md) for component boundaries, CSS ownership, and the separate `frontend/tests/` layout. From `frontend/`, run `npm run format` to format and `npm run format:check` to check formatting alongside lint, typecheck, tests, and build.
