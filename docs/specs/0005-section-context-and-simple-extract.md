# 0005. Section context for answers and a simple Extract panel

**Date**: 2026-10-07
**Status**: Approved for implementation by the owner on 2026-10-07 ("once you developed spec for improve go and develop it"). Slice 1 done and verified on 2026-10-07; slice 2 in progress.

## Summary

Spec 0004 showed that Extract v2 gives better answers than v1 (40/40 vs 36/40, no losses), but its section structure reaches only the search index, not the answer model. This spec makes two changes:

1. Each piece of evidence sent to the answer model carries its section path. A v2 chunk saying "The notice period is 14 calendar days" then arrives labelled "Part B: Contractors > B.2 Notice period".
2. The Extract panel asks only the questions a non-technical user can answer. Every technical setting moves, unchanged, into a collapsed **Advanced extraction settings** section that shows whether anything differs from the recommended values.

Neither change alters extraction output, saved pipeline versions or indexes.

## Context

- `generation.messages_for` sends `{"label", "text"}` per source. Retrieved evidence already carries `section_path` (`schemas/index.py` `Evidence`), and the chunker already embeds it as a "Section: …" prefix (`chunking._prepared`, `embedding_text`). The text stored and shown to the model leaves it out.
- In spec 0004, v2's handbook answers were all correct but none was supported by the cited text, because the part name existed only in `section_path` (`docs/qa/extract-ab-2026-10-07/manual_scores.csv`, q13–q18).
- The Extract panel (`frontend/src/features/ingestion-pipelines/components/IngestionNodeSettings.tsx`) shows about 20 fields for file sources: strategy, OCR policy, OCR languages, rotation, deskew, DPI, maximum OCR pages, per-page timeout, table evidence, quality policy, warning publication, failed optional items, six quality thresholds and four language-policy fields. The owner's feedback is that end users are not technical and cannot judge what these do.
- With the default quality policy, a single file that fails a check stops the whole run (spec 0004, v1 arm). A user needs to understand that choice in plain words.

## Requirements

### Slice 1: Section context reaches the answer model (backend)

1. `messages_for` adds `"section": "A > B"` to a source when its `section_path` is non-empty. The key order is label, section, text. A source with no section path is sent exactly as before, so answers from indexes without structure (legacy native-text, `character_window`, v1 page-level chunks) produce byte-identical prompts.
2. Both places that serialize sources use the same helper: the template's `{context}` substitution and `untrusted_evidence`.
3. The section text is document-derived and untrusted, like the chunk text. It stays inside the JSON data payload and is never interpolated into instructions. The system prompt is unchanged.
4. The context budget (`build_context`, `prompt_bound`) includes the section text, so a long path can never push the prompt over capacity.
5. The query snapshot records `context_format`: `"label-text-v1"` when no included source has a section, otherwise `"label-section-text-v1"`. Old snapshots are not rewritten.
6. Citations, evidence storage, retrieval and the evaluator are unchanged.

**Verification:**

- Unit tests: a section is included and ordered correctly; a source without a section serializes exactly as before; the budget counts the section; the template substitution includes it; `context_format` is recorded in both cases.
- Rebuild the backend and re-ask the 40 spec 0004 questions through the same v2 answer pipeline version (round 2, about $0.03). Label the new v2 answers blind against the round-1 v2 answers. **Done when** v2 handbook answers (q13–q18) are supported by their cited evidence in at least 5 of 6 cases, overall correctness does not drop, and unanswerable questions are still declined.

**Result (2026-10-07):** 5 new unit tests pass, and 71 query, pipeline, experiment and comparison tests pass on the isolated PostgreSQL stack. Round 2 asked the 40 questions again through the same v2 answer pipeline for $0.0248. All 40 answers were correct or correctly declined, as in round 1. Handbook answers supported by the evidence the model received rose from 0/6 to 6/6, and all answerable questions from 24/34 to 30/34. Details: `docs/qa/extract-ab-2026-10-07/round2/`.

### Slice 2: Simple Extract panel (frontend)

For sources that read files (uploads, S3), the panel shows, in this order:

1. A one-line plain explanation: "Text, tables and headings are read automatically. Scanned pages are read with OCR when they have no text layer."
2. **Read scanned pages (OCR)**, a checkbox that maps `ocr.mode` between `auto` (checked) and `off`. A saved `always` mode shows as checked, and the checkbox keeps it unless the user unchecks it. When OCR is unavailable on the server, the checkbox is disabled and shows the server's reason.
3. **Languages in scanned pages**, shown only when OCR is on. These are the existing language checkboxes, with readable names for known codes ("English (eng)") and the raw code otherwise.
4. **If a file can't be read well**, a select with:
   - **Stop and let me review**: the `default-v1` policy from capabilities (the recommended default).
   - **Publish the other files and show warnings**: the `warn-v1` policy.
   - **Custom (see Advanced)**: shown, and selected, only when the saved policy is neither preset unchanged (for example `strict-v1` or edited thresholds). It cannot be chosen; it only reflects the saved value.

   Under the select, one sentence explains the selected choice in plain words.

For sources that do not read files (website, Notion, Confluence), the panel shows the existing "Quality and language only" note and item 4.

Everything else, unchanged and with the same labels, moves into a `<details>` section titled **Advanced extraction settings**: extraction strategy, OCR policy, rotation, deskew, OCR resolution, maximum OCR pages, per-page timeout, table evidence, quality policy, warning publication, failed optional items, quality thresholds and language policy. The upgrade callout and the legacy native-text view stay where they are.

- The collapsed summary line reads "Using recommended settings" or "N settings differ from recommended" and lists their labels.
- **Reset to recommended**, inside the section, restores the recommended values for every advanced field except OCR languages and `config_version`. It is shown only when something differs.
- The section opens automatically when any advanced field has a server validation error, so errors are never hidden.
- Recommended values are the ones `defaultIngestionDraft` uses today: strategy `auto`; OCR `auto` when available; rotation and deskew on; 200 DPI; `min(server maximum, 50)` OCR pages; 30-second timeout; tables `preserve`; the `default-v1` quality policy from capabilities; the default language policy. Both the new-draft defaults and the comparison use one shared function in `editorModel.ts`.

**Verification:**

- Vitest: the simple controls write the same values as the advanced ones; a saved `always` OCR mode survives; the Custom option appears only for non-preset policies; the deviation count and reset; auto-open on an advanced validation error; the page-source variant; every existing test still passes (labels unchanged).
- Playwright: update journeys that operate advanced fields so that they open the section first. Run the affected ingestion editor journeys on the isolated e2e stack.
- Browser check at `http://127.0.0.1:5273` on desktop and phone width, in light and dark themes.

## Out of scope (recorded from spec 0004)

- **Heading-only chunks.** v2 emits chunks such as "Part A: Employees" on their own. Merging them into the following section changes chunk output, so it needs a new chunker version.
- **Table headers across pages.** A table that continues on a new page loses its header in both versions. Fixing this changes extraction output, so it needs a new extractor version.
- The guided setup's Processing step and the documentation site screenshots of the Extract panel. Update them in a follow-up if the owner keeps this design.
- Any change to extraction, chunking, quality evaluation or saved versions.

## Risks

- **Prompt change for existing answer pipelines.** Answers over structured (v2, `section_token`) indexes change because the model now sees section paths. This is intended. The snapshot's `context_format` makes it visible, and indexes without sections are unaffected.
- **Hidden settings.** Moving fields into a collapsed section could hide a non-default saved value. The summary line names every differing field, and validation errors open the section.
