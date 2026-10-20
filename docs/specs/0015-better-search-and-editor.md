# 0015. Better search and a clearer ingestion editor (7 → 8.5 and 8 → 8.5)

**Date**: 2026-10-18
**Status**: Approved 2026-10-18. D1 was decided by the owner (the reranker is a node), and D2-D8 were approved as recommended. Slice 0 done 2026-10-18: `google/gemini-2.5-flash-lite` over vector top 30 meets the retrieval target on A6p (75 of 77, rank 1 +18, no loss), so D2 picks it and S2 is not built under D3 ([results](../qa/search-and-editor-2026-10/README.md)). Slices 1 (Rerank node), 3 (v5 chunkers) and 4 (links, Searched as, run versions) done 2026-10-18, and Slice 5 (pipeline list, phone editor, plurals) 2026-10-20; Slice 6 (proof round) next. Handoff for a new session: [`0015-handoff.md`](0015-handoff.md).

## Summary

The owner rated two areas below the 8.5 target:
- search quality on top of ingestion, at 7/10;
- the ingestion editor UI, at 8/10.

This spec raises both, measuring before building, as in specs 0010-0014.

## Part 1: search quality

### Where search fails today

These are the 77 answerable real-source questions, with retrieval counted as the reference phrase in the top 5.

**Top-5 misses by round:**
- **A5** (current defaults: `layout-ocr-v5`, `section-token-v3`, vector top 5) misses 9: w4-q7, f1-q3, f2-q9, f2-q10, f5-q2, f6-q1, g3-q2, g8-q1, g8-q2.
- **A6p**, the best round so far (`layout-ocr-v6`, `parent-child-v4`), misses 6: w4-q7, f1-q3, f2-q9, f6-q1, g8-q1, g8-q2.
- 22-26 more questions are found only at ranks 2-5.

**Earlier attempts:**
- **Hybrid with BM25 (spec 0013 Slice 0)** found f1-q3, g8-q1 and g8-q2 and put seven more at rank 1. But plain rank fusion lost w1-q1 and g5-q2, so it was not built.
- **One passage per table row (`section-token-v4`, spec 0014)** found f2-q10 and g3-q2. But it split answers that span several rows (DfT f6-q1, f6-q2) and misread an Excel sheet whose first row is a title (NISRA g5-q2).

**Why it fails:**
- **The ranking itself.** Vector similarity alone cannot tell look-alike rows and sections apart, and keyword matches added by plain fusion push some good vector hits out of the top 5.
- **The search runs once with no second look.** A reranker reads the question and each candidate passage together, and is the standard fix for both cases.
- **Tables are still chunked one way for every question.**

### Target for 8.5

On the same questions, indexes and answer model:
- **Retrieval:**
  - at least **74 of 77 in the top 5**, against 68 for A5 and 71 for A6p;
  - **rank 1 up by at least 10**;
  - **no question lost** that A5 or A6p found.
- **Answers:** scored blind with the spec 0004 rubric, at least **3 more correct** than the A5 baseline, with **no correct answer lost**.
- **Cost and speed per question, measured:**
  - added query cost at most $0.002;
  - added median latency at most 1.5 s.

### Proposed changes

- **S1. An optional Rerank node in the answer pipeline (owner decision 2026-10-18: "Reranker it should be as Node only").**
  - **Graph:** a new execution schema version 3 allows exactly one shape besides today's: Question → Retriever → **Rerank** → Prompt → LLM → Answer. Schemas 1 and 2 keep exactly five nodes and run exactly as saved. The graph stays a fixed linear template with one optional node: no branches, no other new node types, and no code in nodes.
  - **Node settings:** `model` (an approved OpenRouter chat model) and `top_n`, the passages it keeps (default 5, 1-20). With a Rerank node present, the Retriever's Top k is the number of candidates it fetches: default 30, at most 50, and at least `top_n`.
  - **What it does:** the model reads the question and the candidates (as untrusted data, never instructions) and returns their order. The node keeps the first `top_n`, and the Prompt receives them in that order. It needs no new dependency, provider or key: it uses the project's OpenRouter key and approved-model list.
  - **Record:** each run records the node's model, prompt version (`rerank-v1`), candidate count, each passage's retriever rank and reranked rank, and the node's own cost and latency, separate from the answer's. The evidence inspector shows both ranks.
  - **Failure:** if the rerank call fails or returns an unusable order, the node passes on the retriever's first `top_n` and the run says "Reranking failed; retriever order used". The answer never fails because of it.
  - **Everywhere the graph runs:** the same compiled graph runs in Playground, experiments, deployed answers and the widget, so every path gets the node through `backend/app/pipelines/langchain_rag.py`. Experiment snapshots include it.
  - **Editor:** the Retriever's settings offer **Add a rerank step**, which inserts the node (and **Remove rerank step**). The node has a labelled, keyboard-accessible settings form like the others, and the canvas draws it with its own icon.
- **S2. Keyword candidates for the reranker (only if Slice 0 shows they are needed).** The candidates are the union of vector top 30 and BM25 top 30, using spec 0013 Parts A-B (term statistics per index version, BM25 ranking). The reranker, not rank fusion, decides the order, which removes the fusion losses spec 0013 measured.
- **S3. Tables that serve both kinds of question (`section-token-v5`, `parent-child-v5`).**
  - Each table keeps its v3 whole-group passage and also gets the v4 row passages, so a question about one row finds the row, and a question about a list across rows finds the table.
  - A spreadsheet or table whose first row has text in only its first cell (a title) takes the next row with mostly filled cells as its header (NISRA).
  - v1-v4 stay as saved.
- **S4. Defaults for new pipelines.** They switch only to what the proof round shows loses nothing: extractor, chunking, reranker on or off, and the candidate source.

**Not in Part 1:**
- query rewriting;
- per-language stemming;
- vector stores other than pgvector;
- answers declined although the evidence is retrieved (f5-q3, f2-q10 in A6p). Those are answer-policy behaviour, measured by the separate 54-question check.

## Part 2: ingestion editor

### What the review found (browser, 2026-10-18, desktop 1,440 px and phone 390 px)

1. **Pipeline list** (46 pipelines in the real-source project):
   - every row shows the same "Ready to run" badge;
   - there is no last-run outcome or time, no published index or version, no search, no filter and no paging.
2. **Phone editor:** the header, buttons and run strip take about 60% of the first screen, and the canvas starts below 500 px of 844.
3. **A pipeline link without `?kind=ingestion`** opens the ingestion pipeline in the answer editor, which fails on its node types and shows a blank page.
4. **The chunk preview** does not show what a passage is searched as when that differs from its text (spec 0014 row passages show neither the searched text nor the section prefix). Run details do not name the extractor and chunking versions a run used.
5. **Wording:** "1 chunks ready" and similar plurals in the source file list.

### Proposed changes

- **U1. Pipeline list:**
  - each row shows the last run's outcome and time, and the published index and version (or "Never run");
  - a search box and an outcome filter (all, complete, failed, running, never run);
  - newest first, with 25 per page;
  - the list API returns these fields in one request, project-scoped and paginated.
- **U2. Phone editor:**
  - one line holds the name, version and **Run ingestion**;
  - **Preview processing**, **Save version** and history move into the existing "…" menu;
  - the run strip collapses to one line ("Last run Complete · index v1 ready") with **Run details**;
  - the canvas starts within the first 40% of the screen;
  - desktop is unchanged.
- **U3. Links:**
  - a pipeline link opens the editor for the pipeline's saved kind, whatever the URL says;
  - an unknown or wrong ID shows "Pipeline not found" with a link back to the list;
  - an error boundary around the canvas shows a safe message instead of a blank page.
- **U4. What ran:**
  - the chunk preview and the index inspector show **Searched as** (section prefix plus searched text) whenever it differs from the passage text, as for table rows;
  - **Run details** lists the extractor, cleaner and chunker versions of the run.
- **U5. Wording:** singular and plural forms in the source file list, the run strip and the results; no other copy changes.

### Target for 8.5

- Each finding above is fixed and covered by a Playwright journey on desktop and phone.
- No page error, and lint, typecheck, Vitest and build pass.
- An accessibility pass with axe on the list and editor finds no serious or critical issue.

## Decisions for the owner

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | Reranker kind | **Decided by the owner: an optional Rerank node** in the answer graph (schema version 3), between Retriever and Prompt. **Recommended engine: an OpenRouter chat model as a listwise reranker.** It needs no new dependency or key. A local cross-encoder needs about 0.5-1 GB more memory per worker on this machine, and a hosted rerank API needs a new provider and key. |
| D2 | Reranker model | Chosen by measurement in Slice 0 from two candidates: a small, cheap model and `google/gemini-2.5-flash`, the answer model already in use. The reranker orders evidence and does not score answers, so the owner's "no weak LLM judge" rule is not affected. **Pick the cheapest one that meets the target.** |
| D3 | Keyword candidates (S2) | **Build them only if Slice 0 shows vector-only candidates miss the target.** |
| D4 | Tables (S3) | **Build `section-token-v5` and `parent-child-v5`** (whole group plus rows, title-row header) and measure them in the proof round. |
| D5 | Defaults (S4) | **Switch new answer and ingestion pipelines only to what the proof round shows loses no answer and no top-5 hit**, as in specs 0012 and 0014. |
| D6 | Spending | Slice 0 costs about $0.30 (reranking 77 questions with up to two models and two candidate sources), and the proof round about $0.40. **Cap $1.** The real-source harness total is $0.79 of its $2 cap, so it rises to $2.50 for this spec. |
| D7 | Editor order | **U3 and U4 first** (bug and missing information), then U1, U2 and U5. |
| D8 | Pipeline list API | **Add `last_run` and `published_index` to the existing list response**, with `limit`, `offset`, `q` and `outcome` parameters. Old clients ignore the new fields. |

## Slices

| Slice | Content | Acceptance |
| --- | --- | --- |
| 0 | Measure first, paid (about $0.30): rerank the A5 and A6p vector top 30 offline with both D2 models, and with BM25 candidates added. Record top 5, rank 1, losses, cost and latency per question | Results in `docs/qa/search-and-editor-2026-10/`. If no setting meets the retrieval target without a loss, stop and report |
| 1 | S1 Rerank node: schema version 3 and graph validation, execution in the compiled graph (Playground, experiments, deployments, widget), snapshot, fallback, cost and latency, evidence ranks, canvas node and settings form, **Add a rerank step** and **Remove rerank step** | Validation tests for every allowed and rejected shape; schemas 1 and 2 byte-identical; PostgreSQL tests for runs and snapshots; reranker failure falls back and says so; Vitest and Playwright for adding, configuring, saving and removing the node |
| 2 | S2 keyword candidates (only under D3) | Spec 0013 Slices 1-2 acceptance |
| 3 | S3 v5 chunkers | Chunking tests: whole group and rows, title-row header; v1-v4 unchanged |
| 4 | U3 and U4 | Vitest, Playwright for links and Searched as, backend tests for run versions |
| 5 | U1, U2 and U5 | List API tests (scope, paging, filters); Playwright desktop and phone; axe |
| 6 | Proof round, paid (about $0.40) | Rounds A7 (best Slice 0 settings, plus v5 chunking) against A5 and A6p, scored blind; switch defaults only under D5 |

## Verification

- Backend unit and PostgreSQL tests, and the full suite in the isolated stack.
- Frontend lint, typecheck, Vitest with `--maxWorkers=1`, build.
- Playwright on `http://127.0.0.1:5273` on desktop and phone.
- Blind scoring with 10 labels for the owner to spot-check.
- Each slice is committed on local `main`; nothing is pushed until the owner asks.
