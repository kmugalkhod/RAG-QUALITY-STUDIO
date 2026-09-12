# Retrieval node settings — implementation proposal

Status: implemented and verified 2026-09-12. This document retains the agreed scope and acceptance criteria; actual verification and limitations are recorded in [the implementation tracker](implementation-plan.md#retrieval-node-settings--completed-2026-09-12). Supersedes the broader earlier retrieval proposal.

## Outcome and scope

Users configure how Retrieval searches, save immutable pipeline versions, and run the same configuration from the visual editor, Playground and experiments.

Implement exactly six controls: search method, Top k, maximum vector distance, vector candidate count, keyword candidate count and hybrid weighting. Query, index/source binding and end-user filters are inputs. Reranking is a separate node. Query rewriting, diversity selection, context expansion and document-cap controls are outside this increment.

The current graph requires Question → Retriever → Prompt → LLM → Answer and stores `index_id` in the retriever. Preserve this supported graph during the settings increment. Display the existing source selector in an **Inputs** section separate from **Search settings**, retaining its serialized binding. Future typed Knowledge Source and Filter Input connections can supply runtime inputs; implementing those nodes is a separate increment. Do not render unimplemented ports or a Reranker node. This increment improves the existing visual editor; it does not deliver arbitrary graph composition.

## Verified code baseline

- `backend/app/schemas/pipeline.py`: version-1 graph, fixed node order, index ID and Top k.
- `backend/app/services/indexes.py`: ready-index/project checks, saved embedding configuration, exact cosine retrieval and stable tie-break ordering.
- `backend/app/schemas/index.py`: direct retrieval API and evidence with mandatory cosine distance.
- `backend/app/services/queries.py`: snapshots Top k and reconstructs it during deferred execution.
- `backend/app/services/pipelines.py`, `backend/app/workers/experiments.py`: independently pass Top k into query requests.
- Editor, Playground and Knowledge Base search have overlapping forms; experiment summaries also read Top k directly.
- Compose pins pgvector 0.8.0 with PostgreSQL 17. Reuse this stack and providers; add no search service or dependency.

## Configuration contract

Introduce a discriminated, application-owned `RetrievalSettings` schema. These are proposed bounded defaults, not measured optimal settings.

| Control | Field | Rules and default |
| --- | --- | --- |
| Search method | `mode` | `vector`, `keyword`, `hybrid`; default vector |
| Top k | `top_k` | Strict integer 1–50; default 5; maximum output chunks |
| Maximum vector distance | `max_vector_distance` | Optional finite number 0–2 inclusive; default null/off; vector/hybrid only |
| Vector candidate count | `vector_candidates` | Hybrid only; strict integer between Top k and 200; default 50 |
| Keyword candidate count | `keyword_candidates` | Hybrid only; strict integer between Top k and 200; default 50 |
| Hybrid weighting | `vector_weight` | Hybrid only; finite 0–1; default 0.5; keyword weight = 1 minus vector weight |

Reject unknown/inapplicable fields and invalid numbers. UI may remember per-mode drafts, but sends only active settings. Raising Top k beyond a candidate count produces an actionable validation error. Query/source/filter inputs stay outside this object. Top k is retrieval output count, not a reranker's final count. Returning fewer results is valid; never pad results or broaden scope.

## Execution behavior

**Vector:** preserve current exact cosine ordering and stable chunk tie-breaks. Apply `distance <= max_vector_distance` before limiting results when enabled. Use the index's saved embedding model/dimensions. Metric/model switching does not belong here.

**Keyword:** PostgreSQL full-text search over chunk text with fixed `simple` analysis, `websearch_to_tsquery` and `ts_rank_cd`. Match only the selected index's chunks within the project, order by lexical score then stable chunk identity, and limit to Top k. A keyword retrieval-only test calls neither embedding nor answer providers. It still uses a previously prepared ready index; keyword-only ingestion is separate scope. Fixed `simple` avoids silently assuming English stemming, but is not universal multilingual search or guaranteed punctuation-sensitive identifier matching. Test those limitations; true BM25 and language-specific analyzers are deferred.

**Hybrid:** gather bounded vector and keyword candidates with identical project/index restrictions. The distance cutoff applies to the vector branch only; independently matching keyword chunks remain eligible. Explain this beside the control. Deduplicate the union by `(processing_run_id, chunk_ordinal)` and apply weighted reciprocal rank fusion:

`score = vector_weight / (60 + vector_rank) + (1 - vector_weight) / (60 + keyword_rank)`

Ranks start at 1; missing branches contribute zero. Keep the RRF constant 60 fixed and versioned, not another user setting. Sort descending by fused score, tie-break by chunk identity, return Top k. Skip zero-weight branches and exclude zero-contribution candidates. At most 400 candidates enter the union. Never average raw lexical and distance scores.

An active branch failure fails the request/run; do not silently substitute another mode. A successfully empty branch is valid. No final matches produces an explicit no-match result; generation retains the existing insufficient-evidence path without an answer-model call. Preserve cancellation hooks and existing provider limits. Future user filters must apply consistently to every active branch and only narrow server-enforced access.

## Persistence and compatibility

1. Add a GIN expression index through Alembic on `to_tsvector('simple'::regconfig, text)` on immutable chunk text. Use the identical expression in search. Index construction covers existing rows and future inserts automatically; no re-embedding or historical index-membership changes. Test populated upgrades and document build-time/write-lock implications. Enable keyword/hybrid after migration success; inspect query plans with scoped membership joins before claiming scale performance.
2. Retain explicit pipeline schema-v1 parsing/execution. Introduce schema v2 with nested retrieval settings and the existing source binding. Normalize v1 in memory to vector, saved Top k, cutoff off. Do not rewrite historical JSON. Editing/saving creates a new v2 version; merely loading a v1 version must not mark it dirty.
3. Existing direct retrieval/query APIs retain legacy flat `top_k` through an adapter. New requests use `retrieval: {...}`. Reject requests containing both. Normalize once into the shared contract.
4. Persist effective settings, retrieval algorithm version, lexical configuration and RRF constant before deferred execution. Query and experiment workers read snapshots rather than mutable defaults. Legacy in-flight snapshots retain dense behavior.
5. Make cosine distance nullable for evidence lacking a vector score. Add nullable lexical/fusion scores and branch ranks with explicit score semantics. Missing values are null, never fabricated cosine values or confidence. Preserve legacy vector response semantics.
6. Store bounded retrieval outputs/diagnostics separately from the exact evidence supplied to generation, including branch counts, output count and durations. Update inspectors, experiment summaries and exports. Unknown embedding cost remains unknown; keyword search avoids model calls but still consumes database resources.

## Implementation sequence and acceptance criteria

### 1. Shared settings and vector cutoff

Update `schemas/{pipeline,index,query}.py`, `services/{pipelines,indexes,queries,experiments}.py` and `workers/experiments.py` with the common contract, normalization and snapshot propagation. Add cutoff execution and mode-aware evidence. Keyword/hybrid remain unavailable until implemented.

Acceptance: old versions return the same dense order; full settings survive save/reload, previews and deferred/experiment execution; exact cutoff boundaries and empty results work; invalid configurations fail server-side; cross-project and wrong-index requests remain rejected.

### 2. Keyword and hybrid engine

Add the lexical migration and model index declaration, keyword branch and bounded RRF. Keep `services/indexes.py` as the entry point; extract cohesive logic into `pipelines/retrieval.py` if needed. No generic workflow engine.

Acceptance: isolated PostgreSQL fixtures verify lexical matches, identifiers/tokenization, RRF ordering, identity deduplication, weight endpoints, stable ties, candidate limits, empty branches and active-branch failures. Keyword-only retrieval works without embedding credentials on a prepared fixture index and makes zero provider calls. Same-text chunks in another project/index never leak through lexical joins. Migration clean install, populated upgrade, downgrade/upgrade and preservation checks pass without resetting developer data.

### 3. Visual settings and all calling surfaces

Use one shared settings form in `PipelineEditor.tsx`, `PipelineTestSettings.tsx`, retrieval Playground and Knowledge Base `IndexPanel.tsx`; update their API types/adapters and experiment candidate summaries.

- Basic: Search method and “Top k — chunks returned”.
- Advanced: optional cutoff in vector/hybrid; candidate counts and weighting only in hybrid. Provide exact keyboard-editable numbers, label both branch weights, and explain that weighting is influence rather than confidence or a promised percentage of results.
- Inputs: source selector separated from tuning controls. Do not add a metadata-filter setting.
- Node summary: “Vector · Top 5”, “Keyword · Top 5” or “Hybrid · Top 5”.
- Preserve charcoal/lavender styling, unsaved guards, version identity and existing graph coordinates. Mode switches must not submit hidden stale fields. Expose only implemented backend capabilities.

Acceptance: settings actually affect requests/execution; save/reload restores values; discard restores prior settings; errors distinguish validation, no matches and execution failure. Keyboard navigation, labels, desktop/mobile layout and saved-version/preview behavior work. Retrieval-only tests never call generation or reranking.

### 4. Regression and measured comparison

Run PostgreSQL/pgvector tests with deterministic provider mocks, frontend lint/typecheck/unit tests/build, backend Ruff and the documented isolated browser stack. Add a browser journey: load old pipeline → edit retrieval → preview → save new version → reload → execute → inspect mode-specific scores. Cover direct retrieval, background queries and experiments so no path silently falls back to Top k alone.

Compare modes on identical source versions using reviewed exact-term/identifier, paraphrase and unanswerable questions. Label relevant chunks for Recall@k/rank evaluation; record failures and retrieval latency. Existing RAGAS metrics evaluate their supported downstream behavior, not a fabricated retrieval score. Live provider checks remain opt-in and bounded. Keep vector default until measured evidence justifies changing it.

Update implementation status, architecture, API/development documentation and actual verification outcomes. No production-readiness or quality-improvement claim without evidence.

## References and next action

- [PostgreSQL 17 text search controls](https://www.postgresql.org/docs/17/textsearch-controls.html): text analysis, query parsing and lexical ranking.
- [pgvector hybrid search](https://github.com/pgvector/pgvector#hybrid-search): full-text integration and rank fusion.
- [Microsoft RRF scoring](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking): combining rankings and interpreting scores.

Analyzer choice, bounds, defaults and weighted-RRF formula are application design decisions. All four increments are implemented. See the implementation tracker for executed tests and the unperformed live-model/performance comparisons.
