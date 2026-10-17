# 0012. Clean, Chunk, Embed and Publish Index: fewer bugs, simpler panels, faster runs

**Date**: 2026-10-17
**Status**: Approved 2026-10-17. The owner accepted the recommendations for D1-D9. Nothing is built yet; Slice 0 is next.

## Summary

The source and Extract nodes have had their own specs (0005, 0008, 0011). The four nodes after them have not. On 2026-10-17 four read-only audits, one per node, read the frontend, backend, workers and tests. The main findings were then checked again in the code. They found three kinds of problem.

1. **Bugs that lose or misplace data:**
   - "Create a new knowledge set" can publish into an existing one.
   - Every canvas pipeline publishes into the same set, "Ingested knowledge".
   - Chunk settings that pass validation can fail at Embed after the run has already paid for some batches.
   - Website chrome removal can delete short tables and code that repeat across a site.
2. **Panels that are hard to use:**
   - Clean shows 9 raw transforms with up, down and delete buttons.
   - Chunk shows 3 to 5 numbers in "tokens" that are really UTF-8 bytes.
   - A mistake in Chunk settings comes back as 35 validation errors, and none is attached to a field.
   - The literal-text boxes drop every space and new line the user types.
   - The same concept is called "reusable index", "collection", "knowledge set" and "document set".
3. **Slow paths:**
   - Any Clean edit re-extracts every file, including OCR.
   - Embedding sends 16 chunks per request, and each batch runs a `COUNT(*)` over the whole index.
   - Chunk splitting is quadratic on a long block: 11.7 s for one 2 MB block.

This spec fixes the bugs first, then simplifies the panels in the spec 0005/0008 pattern (a few plain choices, everything else under Advanced, Reset to recommended), and then removes the slow paths. Changes that alter output get new versions (`structure-clean-v2`, `section-token-v3`, `parent-child-v3`). They become the default for new drafts only if a real-source round loses no answer, as in spec 0010.

## Decisions for the owner

| ID | Decision | Recommendation |
| --- | --- | --- |
| D1 | One user-facing name for a knowledge set | **"Index"**, with versions ("Index: Python tutorial · version 3"). The answer side's "Documents to search" becomes "Index to search". Code and API names stay `knowledge_set`. |
| D2 | Default destination for new pipelines | The pipeline's own name, not "Ingested knowledge". Saved pipelines keep their saved destination. A saved pipeline that shares a destination with another pipeline shows one line: "Also published by Pipeline X. Each run replaces its current version." |
| D3 | New or existing index | An explicit choice: **New index** (name field) or **Add a version to an existing index** (list). If a new name matches an existing index, saving fails with a field error. A version saved before this spec still publishes by name, as today. |
| D4 | Chunk size units | Show passage size as Small, Medium or Large with "about N words". Keep the exact byte numbers under Advanced, labelled "bytes", not "tokens". The schema keeps its field names. |
| D5 | Chunk sizes the embedder cannot accept | New saves are rejected when the maximum size plus the heading prefix can exceed the provider's 8,191-byte limit. The heading prefix is capped at 300 bytes. Saved versions above the limit still open; they show a warning and can be reset in one click. |
| D6 | Output-changing versions | Build `structure-clean-v2` and `section-token-v3`/`parent-child-v3` in this spec, then prove them on the spec 0006/0008/0009 real-source files (spending cap $1). New drafts switch to them only if no correct answer is lost. Saved pipelines keep their version and see the existing upgrade notice. |
| D7 | Embedding throughput and fairness | Up to 64 chunks per request, within a byte budget. Indexing uses at most 45 of the 60 requests per minute, leaving 15 for Playground and answers. After 15 minutes of continuous throttling a run fails with "The embedding provider kept refusing requests (rate limit)". |
| D8 | A refresh with no content change | Publish no new version when the membership equals the current version. The run succeeds with "No changes; version N stays current". This saves storage and embedding writes. Nothing is deleted. |
| D9 | Sensitive-data redaction | It stays on by default but is visible on the Clean panel, as a plain line with a toggle, rather than hidden in a collapsed section. |

## Part A: bugs (no output change)

Each item names its evidence. "Fix" says what changes.

### Publish Index
- A1. **A "new" set inherits an existing name.** Picking an existing set copies its name. Switching back to "Create new" keeps it, and the backend then resolves the name to the existing set (`frontend/src/features/ingestion-pipelines/components/IngestionNodeSettings.tsx:835-846`, `backend/app/services/ingestion.py:160-171`). Fix: D3.
- A2. **Every canvas draft defaults to "Ingested knowledge"** (`editorModel.ts:605, 695, 951`). Fix: D2.
- A3. **A race returns 503 instead of 409.** Two starts can race, for example a schedule and a manual run. The losing one hits a unique constraint, and `main.py:187-196` maps that error to 503 "Database unavailable". Fix: lock the knowledge-set row and check again, and map the remaining `IntegrityError` to 409 with a clear message.
- A4. **Stale recovery leaves states half-written.** When the dispatcher fails a stale run (`backend/app/workers/dispatcher.py:186-250`), node states and the source snapshot stay "running" or "collecting", and run items are not cancelled. Fix: call the same terminal helpers that a normal failure uses.
- A5. **Unpublished indexes show a version.** `published_index_id` and `version` are returned for indexes that are not ready (`services/ingestion.py:646-680`), and the group strip shows "· version N" for failed branches (`IngestionGroupStrip.tsx:124-127`). Fix: return them only for a succeeded index. Add `prior_index_version` and `is_current` (additive).
- A6. **A current index can belong to a failed run.** The pointer moves before the run is finalized, and a later coordinator error fails the run (`workers/ingestion.py:43-87`). Fix: once the index has succeeded, finalize the run as succeeded. Record a later bookkeeping error as a run warning.
- A7. **Name rules disagree.** Validation compares names ignoring case, but the database is unique by exact case, so "Docs" and "docs" become two sets. Fix: compare ignoring case at resolution too. A clash gives a field error.

### Embed
- A8. **Valid chunk settings can fail at Embed.** `maximum_tokens` may be up to 16,384 bytes (`backend/app/schemas/ingestion.py:912`), the heading prefix is not counted (`backend/app/ingestion_content/chunking.py:381`), and the adapter rejects inputs over 8,191 bytes (`backend/app/providers/openrouter.py:25-33`). Fix: D5. The Embed error names the source, page and chunk.
- A9. **Persistent throttling never ends.** A throttled batch requeues without counting a failure (`backend/app/workers/indexing.py:251-255`), and the coordinator's poll keeps the run fresh, so stale recovery never fires. Fix: D7's 15-minute cap.
- A10. **The reason for a wait is hidden.** The coordinator clears the run error on every pass and copies only counts (`workers/ingestion.py:181, 326-337`). Fix: show "Waiting for embedding request budget, resumes in 20 s" or "Retrying after a provider error (2 of 3)" on the run strip.
- A11. **Paid work goes unreported.**
  - Usage from a successful request is dropped when the run was cancelled, because the worker returns before adding it (`indexing.py:170-181`).
  - Failed and cancelled runs show no usage at all (`IngestionRunStrip.tsx:108`).

  Fix: record usage before the cancel return, and show usage, or "unknown", on every terminal run.
- A12. **A pipeline saved under an older server embedding model is a dead end.** It gets a 422 at run start (`backend/app/services/pipelines.py:304-317`) and offers no way out. Fix: a mismatch badge and **Use the server's embedding settings**, which creates a new version, as the Chunk upgrade does. The editor also opens a saved pipeline read-only when the embedding key is missing, instead of refusing (`IngestionPipelineEditor.tsx:249-253`).

### Chunk
- A13. **A Chunk mistake produces 35 errors and no field error.** The node union has no discriminator (`schemas/ingestion.py:976-987`), so one bad value reports errors for every node type. The frontend shows the first 5 (`frontend/src/lib/api.ts:96-108`) and maps no Chunk field (`editorModel.ts:432-458`). Fix: discriminate on `type`. Map `target_tokens`, `maximum_tokens`, `overlap_tokens`, `child_*`, `parent_*`, `size` and `overlap` to their inputs with `aria-invalid`. Check in the client that the values are whole numbers, that overlap is below the target, and that the target is at most the maximum. An empty number field is invalid, not `0`.
- A14. **v1 configs record the v2 engine name.** `chunker_version_for_node` always returns `section-token-v2`/`parent-child-v2` (`backend/app/ingestion_content/processing.py:25-26, 200-209`), so a v1 pipeline displays "chunker section-token-v2". Fix: add the saved `config_version` to the processing record and show that. The engine label stays, so existing hashes and reuse keep working.
- A15. **Character-window defaults disagree:** 1000/100 in the panel, 800/120 in capabilities (`IngestionNodeSettings.tsx:290-298`, `backend/app/extractors/pdf.py:372-381`). Fix: read capabilities everywhere.
- A16. **Switching the chunking method silently discards edits** (`IngestionNodeSettings.tsx:254-300`). Fix: a one-line notice with Undo.

### Clean
- A17. **The literal, selector and pinned-location boxes drop typed spaces and new lines.** They are controlled through `lines()`, which trims each line and removes empty ones (`frontend/src/features/ingestion-pipelines/components/CleaningTransformSettings.tsx:81-86, 309-345`; `IngestionNodeSettings.tsx:1490-1502`). Fix: keep the raw text in local state and parse it when the field loses focus or the pipeline is saved.
- A18. **"Preserve structured blocks" can be unchecked, but that changes nothing.** Protection starts from the default set and a disabled step is skipped (`backend/app/ingestion_content/cleaning.py:534-541`). The toggle still changes the config hash, which forces re-extraction. Fix: remove the toggle from the panel. `structure-clean-v2` (Part D) defines the behaviour.
- A19. **"Add transform → Remove literal boilerplate" saves the placeholder "Replace this literal"** as a real value (`CleaningTransformSettings.tsx:62`). Fix: start empty. An empty list is invalid.
- A20. **Clean server errors are never shown on a field,** and messages use raw IDs ("unicode_normalize must run before dehyphenate.", `schemas/ingestion.py:865`). Fix: map errors to the step and field, with plain wording.
- A21. **The "Words dehyphenated" metric counts kept compounds** (`cleaning.py:287-289`). Fix: count only joined words. This changes a metric, not the text.
- A22. **The guided-setup hint is wrong.** It says both cleaners remove menus (`GuidedSetupSteps.tsx:435`), but the compatibility cleaner does not. Fix: new drafts offer only Structure-aware. Saved compatibility pipelines keep it.

## Part B: simpler panels (UI only; saved pipelines run as saved)

The pattern of spec 0008, D1:
- The schema keeps every field.
- New drafts and **Reset to recommended** produce the recommended values.
- A saved custom value stays as saved and is listed under Advanced as "N changed".
- Nothing is silently rewritten.

| Node | Visible | Advanced (collapsed, "N changed", Reset) |
| --- | --- | --- |
| Clean | One sentence of what runs ("Removes website menus, cookie banners and repeated page headers; keeps tables, lists and code"); text to remove (literal lines); "Redact emails, phone numbers and IDs" toggle (D9); an older-profile notice like Extract's | The transform list in the server order, each with on/off and its fields, no reorder or delete; "Skip duplicate pages or files" (renamed duplicate policy); length limits |
| Chunk | Method: Section-aware (recommended) or Parent and child ("better for tables and short facts"); passage size Small / Medium / Large with "about N words" (D4); the upgrade notice; a **Preview chunks** link | Exact byte sizes, overlap, heading context ("Help search find passages by their section title; not shown in answers"), character window for saved pipelines |
| Embed | "Uses openai/text-embedding-3-small (1536 dimensions), set by the server"; after a preview: "about N chunks, about X bytes, estimated $Y (list price, estimate)"; after a run: "N new, M reused, cost $Z or unknown"; mismatch badge (A12) | None |
| Publish | New index or Add a version (D3); "This run publishes version N+1 of *Index*. Version N stays available. Answer pipelines keep their version until you switch."; who else publishes here (D2) | None |

Requirements:
- B1. **Canvas summaries say what was chosen,** not counts: "Recommended" or "Recommended · 2 changed" instead of "9 ordered transforms".
- B2. **The chunk preview gains a summary:** count, median, minimum and maximum size, short chunks under 40 bytes, and chunks over the embed limit.
- B3. **After a run:**
  - The run strip and Run details say "Replaced version M; it remains available", or "Version M is still current" after a failure or cancel.
  - The group strip gets **Use in answer pipeline**.
- B4. **Every panel works by keyboard and screen reader:** labels, `aria-invalid`, and field errors linked with `aria-describedby`. It holds at phone width, in both themes.
- B5. **Docs are updated:** `docs/site/docs/ingestion/` cleaning, chunking, a new embedding page (the Embed "About this stage" link points to the chunking docs today) and publishing.

## Part C: performance (output stays byte-identical unless stated)

| Item | Today | Change | Check |
| --- | --- | --- | --- |
| C1. Chunk splitting | `_split_ranges` rescans every boundary for each range (`chunking.py:95-97`); `prefix_end`/`suffix_start` encode one character at a time (`tokenizers.py:26-55`). One 2 MB block takes 11.7 s | Use `bisect` over the boundaries and precomputed byte offsets | Golden test: v1/v2 output unchanged on the corpus; 2 MB block under 1 s |
| C2. Clean page metrics | O(pages × blocks) loops (`cleaning.py:663-670`, `canonical.py:135-137`, `sensitive_data.py:336-352`): 2.6 s for 1,000 pages × 20k blocks | One pass with a counter | Corpus digests unchanged |
| C3. Control-character removal | A Python loop per character (`cleaning.py:208-223`): 0.64 s per 2 MB | A precompiled regex fast path | Corpus digests unchanged |
| C4. Website fingerprints | `list(documents)` holds every page in memory and each page is extracted twice (`cleaning.py:114`, `remote_ingestion.py:556-563`) | Stream the pages and keep the extraction for the processing pass | Memory flat on a 200-page site; output unchanged |
| C5. Reuse across Clean edits | Extract and clean share one hash, which includes the duplicate and redaction policies (`processing.py:254-276`), so any Clean edit re-runs extraction and OCR | Give extraction its own reuse key, and remove the after-clean policies from the cleaning hash | Changing a Clean setting re-runs no OCR; each existing pipeline misses the reuse cache once |
| C6. Embedding batches | 16 per request; a new HTTP client per request (`openrouter.py:40`); one `session.get` per row; `COUNT(*)` over the index every batch (`indexing.py:182-206`) | Up to 64 per request (D7, after confirming OpenRouter's limit), one client per worker, bulk vector update, a running counter, a partial index for `embedding IS NULL`, and identical texts in a batch sent once | Same vectors and tokens; `test_indexing_throughput.py` shows the gain |
| C7. Membership copy | Up to 100 Python inserts of 500 rows each while the knowledge-set lock is held (`services/indexes.py:169-216`) | A single `INSERT … SELECT` | Same rows |
| C8. Unchanged refresh | Every run copies all vectors into a new version (about 6 KB per chunk) | D8 | No new version when nothing changed |

## Part D: new versions (output changes; D6)

- **`structure-clean-v2`:**
  - Website chrome removal keeps protected blocks (tables, lists, code, quotes, footnotes), and keeps the first copy of a repeated block instead of none (`cleaning.py:440-496`).
  - Fingerprints are taken after Unicode normalization and control-character removal, so soft hyphens no longer break matching (`cleaning.py:479`).
  - One length check, with the measured number in its message, replaces the four checks today.
- **`section-token-v3` / `parent-child-v3`:**
  - Overlap starts at a sentence or word boundary, never mid-word.
  - Hard splits fall back to whitespace, and the sentence ends include "。！？".
  - A remainder under 40 bytes joins its neighbour.
  - The heading prefix does not repeat the heading already at the start of the evidence (`chunking.py:359-404`).
  - Today parents and chunks can start with "inal passengers…" and children can be 80 bytes.
- v1 and v2 of each keep byte-identical output. The existing upgrade notices name the v3 changes.

## Slices

Each slice is committed on its own after its checks pass.

| Slice | Content | Acceptance |
| --- | --- | --- |
| 0 | Baseline, free: per-stage timings from `ingestion_run_nodes` for the 2026-10-17 W1a run and a preview of the spec 0006/0008 files; chunk statistics (count, sizes, mid-word starts, chunks under 40 bytes); one reproduction of each Part A bug as a failing test | Numbers recorded in `docs/qa/clean-chunk-embed-publish-2026-10/README.md`; one failing test per A item that has a backend or frontend path |
| 1 | Publish bugs A1-A7, D2, D3 | Every Slice 0 publish test passes; a new pipeline publishes to its own index; "New" with an existing name gives a field error; a concurrent start gives 409; a stale-failed run has terminal node and snapshot states |
| 2 | Embed and Chunk safety A8-A16, D5, D7 cap | A chunk config that can exceed 8,191 bytes is rejected at save on its field; a bad Chunk value gives one message on its field; throttling ends after 15 min with a clear error; usage shows on cancelled runs; the stale-model pipeline offers the upgrade |
| 3 | Clean bugs A17-A22 | Typing "Page 1 of" and a second line works; no placeholder is saved; Clean errors show on their step |
| 4 | Simpler panels, Part B | Each panel matches the table; Reset restores recommended values; saved custom values survive a save; Vitest covers each panel; a Playwright journey edits Clean, Chunk and Publish, then saves and previews; desktop and phone, both themes, no console errors |
| 5 | Performance C1-C7 | Corpus digests and v1/v2 chunk output unchanged; the timing targets in the table are met; a Clean edit re-runs no OCR |
| 6 | `structure-clean-v2`, `section-token-v3`, `parent-child-v3` (Part D) | v1/v2 byte-identical; v3 has no mid-word starts and no chunk under 40 bytes on the corpus; protected blocks survive website chrome removal |
| 7 | Proof round, about $0.10, cap $1 | The real-source questions rebuilt with v2 cleaning and v3 chunking: no correct answer lost compared with round A4s (38/44); if none is lost, new drafts use the new versions |
| 8 | Unchanged refresh, D8 | A second run on unchanged sources publishes nothing and reports "No changes; version N stays current"; a changed source still publishes |

## Verification

- **Backend:** each new test in the isolated suite (`compose.test.yaml`); the full suite with only the 3 known failures; `ruff check` and format on changed files; migrations checked on a clean database and on upgrade (Slices 1 and 5 may add an index or columns).
- **Frontend:** Vitest, lint, typecheck, build, and Prettier on changed files.
- **Browser:** Playwright journeys in the isolated `rag-studio-e2e` stack. A visual check at 127.0.0.1:5273 on desktop and phone in both themes.
- **Honest limits:** the spec states the measured timings before and after. Paid work is limited to Slice 7.

## Out of scope

- Deleting index versions, retention policies, and "make this version current" rollback. These need their own decision under the evidence-preservation rules.
- Changing the embedding provider or model.
- Hybrid keyword search (the spec 0010 follow-up).
- An ANN index for search.
