# Extract node improvement plan

Status: approved 2026-10-06 (owner accepted D1–D3); Slice 0 done 2026-10-06; Slice 1 next
Scope owner: ingestion Extract stage (backend extractors, schema-v2 Extract node, Extract settings panel)
Related: `docs/robust-ingestion-plan.md` (Phase 2 design this builds on), `docs/ingestion-corpus-baseline.md` (current measured gate), `docs/extract-ingestion-qa-findings.csv` (2026-09-26 QA pass)

## 1. Problem

The Extract node is safe and well bounded, but several behaviors reduce the quality of the text that reaches Clean, Chunk and retrieval. A review on 2026-10-06 rated it 6.5/10: about 9/10 for safety and provenance, about 5/10 for extraction quality.

The Phase 2 corpus gate reports 100% reading-order precedence, but its two-column fixture has one text block per column, so it cannot detect the main ordering defect below.

## 2. Verified findings

Each finding was checked against the code; F1 was reproduced with a generated PDF in the backend container.

| ID | Finding | Evidence | Impact |
| --- | --- | --- | --- |
| F1 | **Two-column pages are interleaved.** `_reading_order()` returns left column then right column, but `_layout_page` then sorts every segment by `(top, left)`, which undoes it. | `backend/app/ingestion_content/extractors/pdf.py:566`. A page with three blocks per column produced `L1, R1, L2, R2, L3, R3`. | Sentences from different columns are joined in the same chunks. Affects papers, reports and newsletters. |
| F2 | **PDF tables are truncated to 25 rows × 10 columns (100 cells, 160 characters per cell), and truncation counts as malformed.** | `_safe_table`, `MAX_TABLE_CELLS = 100`; `malformed += int(truncated)`; `fail_on_malformed_tables=True` in Balanced and Strict. | An ordinary 40-row table fails the default policy; under Review warnings, most of its rows are never indexed. |
| F3 | **PDF headings never become a heading path.** Layout segments do not set `heading_path`, unlike Markdown, HTML and DOCX. The chunker's section key is `(heading path, page)`, so each PDF heading forms its own section, separate from the paragraphs under it. | `_layout_page` has no heading-path field; `chunking.py:42-45` and `_sections()`. | Heading-only fragments, and paragraphs that lose the `Section:` context that section-aware chunking adds for other formats. |
| F4 | **Heading detection is too loose.** Any block with one bold span and at most 500 characters is a heading; the first block of every page can be a title. | `_classify_block`: `any(flag & 16 for flag in flags)`; `ordinal == 0` on every page. | Makes F3 worse once headings feed heading paths. |
| F5 | **OCR output is split line by line.** Tesseract rows are grouped by `(block, paragraph, line)`, so each line becomes a separate `paragraph` block. | `_ocr_page` grouping key. | Fragmented blocks; Clean's reflow has to repair what the extractor split. |
| F6 | **Legacy `native-text-v1` PDF extraction is never measured or quality-checked.** | `extract_document`, `pdf.py:833-841`, skips `measured_document` and `evaluate_quality`. | A scanned PDF on a legacy pipeline produces no findings at all. |
| F7 | **Website (and Notion/Confluence) ignore strategy, OCR and table mode, but the Extract panel still shows them.** | `website_ingestion._canonical_chunks` uses only the quality and language policies; `IngestionNodeSettings.tsx:755` is not source-aware. | Controls that have no effect, contrary to the AGENTS.md frontend rules. |
| F8 | **DOCX tables ignore the `tables` setting** and are written as one `| a | b |` block per row with no header. | `formats._docx_segments`. | A row chunk without its header row loses the meaning of each column. |
| F10 | **Auto loses all structure on plain single-column PDFs.** Auto uses layout blocks only when it detects a table, multiple columns or a native/layout character difference above 25%; otherwise the page becomes one native-text block. Found by the Slice 0 corpus. | `extract_document`, Auto branch (`pdf.py:947-960`); Slice 0 baseline: Auto heading recall 0%. | Auto is the default for robust extraction, so most ordinary PDFs reach Clean and Chunk with no headings, block types or boxes, and the F3/F4 fixes would not reach them. |
| F9 | **Smaller issues.** `installed_ocr_languages()` starts a Tesseract process on every PDF extraction, even with OCR off; the 20-character OCR fallback threshold is hard-coded; image regions on pages that also contain native text are never OCR'd; language detection has stopwords only for en/es/fr/de. | `pdf.py:843`, `pdf.py:896`, `language.py`. | Extra latency per document, plus limited coverage. |

## 3. Decisions

### D1. Fixes ship as a new configuration version, `layout-ocr-v2` (recommended)

`docs/robust-ingestion-plan.md` §5.2 says a run never silently switches extractor behavior. F1–F5 and F8 change the extracted blocks for the same saved settings, so:

- add `config_version: "layout-ocr-v2"` to `ExtractNodeV2`, with its own extractor version string (for example `.../layout-v2/formats-v2`), which flows into the processing hash;
- keep `layout-ocr-v1` behavior byte-for-byte unchanged, so existing pipeline versions, source revisions and indexes reproduce exactly;
- new drafts default to `layout-ocr-v2`; a saved `layout-ocr-v1` node shows **Upgrade extraction** in the Extract panel, which creates an unsaved draft change, and saving makes a new pipeline version;
- reprocessing then happens only when a user saves and runs the upgraded version.

The alternative is to fix `layout-ocr-v1` in place and only bump the extractor version. That is simpler but changes results of already-saved versions on their next run, which the robust-ingestion plan forbids. It is not recommended.

Implementation note: v1 and v2 share one code path. A small frozen behavior object (for example `LayoutBehavior(reading_order_v2=..., table_row_groups=..., heading_paths=...)`) is selected from `config_version`, rather than copying the extractor.

### D2. Legacy `native-text-v1` gets report-only findings

For F6, measure the document and attach findings, but keep the saved publication decision unchanged for `native-text-v1` (findings are shown as warnings, with **Upgrade extraction** as the remedy). This makes problems visible without changing which legacy items publish.

### D3. No new dependency in this plan

PyMuPDF suggests the separate `pymupdf_layout` package for better layout analysis. Adding it needs owner approval plus a license, image-size and determinism review, so it is listed under deferred work (section 6), not in a slice.

## 4. Slices

Each slice is a reviewable vertical change with tests, committed to local `main` after verification. Backend checks run in the isolated test stack (`compose.test.yaml`); frontend checks are lint, typecheck, Vitest and a browser pass at `http://127.0.0.1:5273` where the UI changes.

### Slice 0 — Harder extraction corpus (baseline, no behavior change) — done 2026-10-06

Make the corpus able to detect F1–F5 and F8, and record current numbers as the "before".

- Add synthetic CC0 fixtures to `backend/tests/fixtures/ingestion_corpus/manifest.json` and the generators in `test_layout_extraction.py`:
  - two-column page with at least three blocks per column at offset heights;
  - PDF with title, H1/H2 headings and body paragraphs, including a body paragraph that contains a single bold term;
  - PDF table of 40 rows × 6 columns with a header row;
  - multi-line OCR paragraph scan;
  - DOCX with a header-row table.
- Add metrics to `_corpus_report()`: multi-block reading-order pairs, heading precision/recall, heading-path coverage of body blocks, large-table cell retention, OCR blocks per paragraph.
- Record the current values in `docs/ingestion-corpus-baseline.md` under a dated "Before Extract v2" section. Tests that encode the target behavior are added in later slices; this slice only measures.

**Done when:** the report runs in the test stack and the baseline shows the F1 interleaving (reading-order pairs below 100%) and F2 truncation (cell retention below 100%) as measured numbers.

**Result:** `backend/tests/extract_corpus.py` generates the fixtures and measures them; `backend/tests/test_extract_corpus.py` pins the `layout-ocr-v1` values and the SHA-256 of each non-OCR fixture's output (`extract_v1_golden.json`). Every targeted finding reproduced (reading order 80%, table cell retention 40.65% with a Balanced `fail`, heading-path coverage 0%, two titles, DOCX header coverage 0%, four OCR blocks for one paragraph), and the corpus found F10. Numbers are in `docs/ingestion-corpus-baseline.md`, "Before Extract v2".

### Slice 1 — `layout-ocr-v2` versioning and the reading-order fix (F1)

The first real behavior change.

- Backend: add `layout-ocr-v2` to `ExtractNodeV2.config_version` and its validator (Auto, Native or Layout-aware strategy, as for v1); add the behavior selection from D1; return the new version through `extractor_version_for_settings`.
- In v2, `_layout_page` keeps the order from `_reading_order()` and inserts each table before the first text block whose top edge is below the table's top edge within the same column band, instead of re-sorting all segments.
- Frontend: new drafts and **Enable robust extraction** use `layout-ocr-v2` (`editorModel.ts`, `IngestionNodeSettings.tsx`); a saved `layout-ocr-v1` node shows its version and **Upgrade extraction**; the run and preview views show the exact version used.
- Docs: `docs/site/docs/ingestion/extraction` (version note), `docs/architecture.md` (D1).

**Tests:** v2 multi-block two-column order is `L1 L2 L3 R1 R2 R3`; a table placed between paragraphs keeps its position; v1 output for the existing corpus is unchanged (golden comparison); the processing hash differs between v1 and v2; schema rejects `native_text` with v2; frontend unit test for the upgrade action.

**Done when:** corpus reading-order pairs reach 100% on the new fixture under v2, v1 output is unchanged, and the upgrade flow works in the browser.

### Slice 2 — PDF table row groups instead of truncation (F2)

- In v2, split a PyMuPDF table into row groups that fit the existing 15.5 KB attribute budget. Each group is one `table` block that repeats the header row and records `table_id`, `row_start`, `row_end`, `row_count`, `column_count` and `header_repeated: true`.
- Raise the bounds to a total safety limit, for example 2,000 rows × 50 columns × 1,000 characters per cell per table, still enforced.
- Count as malformed only real failures: `find_tables()` raising, ragged rows PyMuPDF cannot normalize, or tables beyond the safety limit (those are still cut, and the finding names the table and page). Plain splitting is not a finding.
- `tables` mode (`preserve`, `markdown`, `plain_text`) applies to every group.

**Tests:** 40×6 table yields multiple groups, 100% of cells retained, header in each group, no `malformed_tables` finding under Balanced; table beyond the safety limit produces the finding; row groups survive Clean (`preserve_structure`) and stay within chunk maximum tokens; v1 truncation behavior unchanged.

**Done when:** large-table cell retention is 100% on the corpus and Balanced publishes the 40-row fixture.

### Slice 3 — PDF heading classification, heading paths and structure under Auto (F3, F4, F10)

- Heading rules in v2:
  - bold counts only when bold spans cover at least 80% of the block's characters;
  - a heading is at most 200 characters and three lines, and does not end with a sentence terminator unless numbered (`1.2 Scope`);
  - `title` only for the largest-font block on the first page;
  - heading level from document-wide ranking of distinct heading font sizes (largest = level 1, at most 6 levels).
- Keep a heading stack across pages and set `heading_path` on every following block, the same way `formats._markdown_segments` does.
- In v2, Auto uses the layout blocks for every page with native text, and falls back to the single native block only when layout extraction loses text (layout characters more than 25% below native). The page's `fallback_reason` records which was used.
- No chunker change is needed: once body blocks carry the heading path, `_sections()` groups a heading with its paragraphs.

**Tests:** a paragraph with one bold term stays a paragraph; H1/H2 levels and paths are correct; heading path continues across a page break; the chunk preview for the fixture starts body chunks with `Section: …`; heading precision and recall measured on the corpus; v1 unchanged.

**Done when:** heading-path coverage of body blocks is above 95% on the heading fixture under both Auto and Layout-aware, exactly one title block is detected, and no heading-only chunks are produced for it.

### Slice 4 — OCR paragraph blocks and lower overhead (F5, part of F9)

- In v2, group Tesseract rows by `(block, paragraph)`, join lines with `\n` in reading order, and keep per-line boxes in bounded attributes for the inspector.
- Cache `installed_ocr_languages()` per worker process with a short expiry (for example five minutes), and skip the call when OCR mode is `off`.
- Keep the 20-character fallback threshold, but record it in page metadata as `fallback_threshold_characters` so inspectors show why a page was OCR'd.

**Tests:** multi-line OCR paragraph is one block; confidence is the mean over its words; character error rate unchanged or better versus the Slice 0 baseline; OCR-off extraction runs no Tesseract subprocess (mocked).

**Done when:** OCR blocks per paragraph is 1 on the corpus fixture and the OCR character-error gates in the baseline still pass.

### Slice 5 — DOCX tables follow the table setting (F8)

- Extend the structured-format extractor (`formats-v2`, used only under `layout-ocr-v2`) so DOCX tables are built as whole tables with the same row-group rendering as Slice 2, including the header row and `tables` mode.
- Check CSV, TSV and XLSX use the same header-repeating groups; align them only if they don't already.

**Tests:** DOCX table renders as Markdown with header in each group, and as tab-separated text in `plain_text` mode; `formats-v1` output unchanged for v1 pipelines.

### Slice 6 — Legacy native-text findings (F6)

- Run `measured_document` and `evaluate_quality` on the `native-text-v1` path with the decision forced back to its previous value (D2), so findings are attached and visible but publication does not change.
- The Extract panel and run results show these findings with **Upgrade extraction** as the remedy.

**Tests:** a no-text PDF on `native-text-v1` reports `no_extractable_text` and `empty_pages` findings and keeps its previous decision; run results render the findings.

### Slice 7 — Source-aware Extract panel (F7)

- When every source in the pipeline is Website, Notion or Confluence, the Extract panel shows only the quality and language policies, with one line saying that strategy, OCR and table settings apply to uploaded files and S3 documents. When any source is Existing files or S3, all controls show, each PDF-only control labeled "PDFs only".
- Saved values are kept, not stripped, so changing the source back restores them and no new pipeline version is created by opening the panel.
- Server behavior is unchanged; this is presentation only.

**Tests:** Vitest for each source mix; browser check of a Website pipeline and an Existing files pipeline on desktop and at 390px.

### Slice 8 — Release baseline and docs

- Regenerate `docs/ingestion-corpus-baseline.md` with an "Extract v2" section next to the Slice 0 numbers.
- Update `docs/site/docs/ingestion/extraction` and the API reference (`generate_api_reference.py --check`), `docs/implementation-plan.md` status and `docs/architecture.md`.
- Run the Extract-related rows of `docs/extract-ingestion-qa-findings.csv` again against v2 and record the results.

## 5. Acceptance criteria (whole plan)

- `layout-ocr-v2` is the default for new drafts; `layout-ocr-v1` and `native-text-v1` saved versions produce exactly the same extracted blocks as before (golden tests).
- On the extended corpus under v2: reading-order pairs 100%, large-table cell retention 100%, heading-path coverage above 95% of body blocks, one OCR block per paragraph, and the existing OCR character-error, native-preservation and determinism gates still pass.
- Balanced policy publishes a document with a 40-row table without a `malformed_tables` finding.
- The Extract panel never shows a control that has no effect for the pipeline's sources.
- Every slice has passing backend tests in the isolated stack, frontend lint, typecheck and tests where touched, and a browser check where the UI changed.

## 6. Deferred (not in this plan)

- `pymupdf_layout` or another layout model (needs dependency approval, D3).
- OCR of image regions on pages that also contain native text.
- Configurable OCR fallback threshold in the Extract panel.
- Language detection beyond script plus en/es/fr/de stopwords.
- Merged-cell and multi-page table stitching.
