# 0009. Extractor v5: charts are not tables, and tables keep their caption

**Date**: 2026-10-10
**Status**: Draft 2026-10-10. The owner approved changes A and B (decisions 1 and 2 after spec 0008). D1 and D2 are open; neither blocks Slices 0-3.

## Summary

Spec 0008's real-file round A2 (`docs/qa/extract-v4-2026-10/README.md`, Slice 6) left two failures that come from extraction:

1. **Charts read as tables.** PyMuPDF's table finder takes a chart's gridlines for a table. In the French Eurostat report, three charts become tables of 52 to 57 mostly empty columns, which exceed the 50-column limit, count as malformed and stop the file under **Stop and let me review**. Text inside a detected table's box is dropped, so chart callouts such as "381 décès pour 100 000 habitants" never reach the index.
2. **Appendix tables without context.** v4 reads the sideways Census Table A-2 row by row, correctly, but neither A2 question about it was retrieved. The row chunks carry the section path "… > Endnotes", because a heading on p. 20 runs on over the whole appendix. The caption "Table A-2. Households by Total Money Income…" is read as a plain paragraph (the caption rule only knows `Table 1`, not `Table A-2`), and the rebuilt rows do not repeat their column header.

This spec fixes both in a new extractor version, `layout-ocr-v5`, and proves it on the A2 files and questions plus a wider set of files.

## Measurements behind the design (2026-10-10, v4, local)

Every table `find_tables` detects in the three test PDFs that have any (122 tables), by share of non-empty cells:

| Share of cells filled | Count | What they are |
| --- | --- | --- |
| under 30% | 52 (41 Eurostat, 9 Census, 2 BERT) | Eurostat: charts and chart legends, including all three "malformed" tables (0.1-2% filled). Census: regions on the pages of Figures 2, 3, 5, 6 and C-1, and the masthead box on p. 3. BERT: fragments of Figure 1 and an appendix figure. |
| 30-44% | 4 | Small Eurostat chart fragments (icons with a number) |
| 45% and over | 66 | Real tables: every Census summary and appendix table (45-73%, 447-5,890 characters), the Eurostat country list, and small figure fragments |

BERT's results tables are borderless and are not detected as tables at all; they are read as text in v1-v4 and stay so.

## Decisions for the owner

| ID | Decision | Recommendation |
| --- | --- | --- |
| D1 | Non-English OCR language pack | Not in this spec: keep recording non-English scans as untested. Adding a pack changes the backend image and can be its own small change. |
| D2 | Files for the wider round (Slice 4) | The owner names the document types users will upload. Without an answer, use 10-15 public files with a clear licence across: annual report with charts, government form, scanned letter, slide deck with charts, spreadsheet export as PDF, contract or policy document, academic paper, technical manual. Spending cap $1. |

## Part A: charts are not tables

- A1. In v5, a detected table with fewer than 30% of its cells filled is not a table. It is not counted in the table count or as malformed, and it creates no table block.
- A2. Text inside such a chart region is read as ordinary layout blocks in reading order, except blocks made only of numbers, signs and short codes (axis ticks such as `1 500`, country codes such as `BG`), which are left out as v4 leaves them out today. Blocks with words (titles, callouts, legends with words) are kept.
- A3. Tables at 30% filled or more are unchanged from v4.
- A4. The page records how many chart regions it skipped (`chart_regions` in the page's layout attributes) so the inspector and tests can see the decision.

Code: `_layout_page` in `backend/app/ingestion_content/extractors/pdf.py` (the `find_tables` loop and the text-block exclusion by table box).

## Part B: tables keep their caption and header

- B1. **Caption.** A block that starts with a table caption, `Table` or `Tableau` followed by an identifier such as `1`, `A-2`, `3.1` or `II`, and is directly followed by a table block on the same page, is the table's caption. All blocks of that table carry the caption (its first line and title, at most 300 characters) as the last element of their heading path and in `table.caption`.
- B2. **Run-on headings.** For the blocks of a captioned table, the caption takes the place of the deepest heading in the path when that heading started on an earlier page. A heading on the same page stays.
- B3. **Continuation pages.** A caption ending in "—Con." or "(continued)" names the same table on a later page and follows B1 and B2.
- B4. **Header rows for rebuilt tables.** A table rebuilt as word rows (v3 merged columns, v4 sideways pages) repeats its header lines at the top of each row group. Header lines are the lines above the first data line, where a data line is one whose words are mostly numbers. Groups stay within the 2,000-row and 50-column limits.
- B5. Other blocks keep their v4 heading path. A caption with no table after it stays a paragraph or image caption, as in v4.

Code: `_classify_block_v2`, `_heading_structure`, `_word_rows`/`table_row_groups` use in `_layout_page` (all in `pdf.py`).

Rules: v1, v2, v3 and v4 output stays byte-identical (golden digests, the corpus test, the v3 table and v4 tests unchanged). The website reader and the DOCX/PPTX reader (`formats-v3`) are unchanged in v5. New drafts switch to v5 at the end of Slice 3; until then the backend accepts `layout-ocr-v5` but the editor creates v4.

## Part C: proof

- C1. Re-run the A2 setup as round A3 with v5: the spec 0006 files under "Stop", and the four spec 0008 files under **Stop** as well (Part A should make Eurostat pass), plus the D2 files on their own track.
- C2. Questions: all A2 questions, plus new questions written from the D2 files before the run (including unanswerable ones).
- C3. Add the results to the workbook as an "Extract v5" sheet beside "Extract v4".

**Done when:** the Eurostat report publishes under "Stop"; the Eurostat chart callout (f4-q1) and both Census Table A-2 questions (f2-q9, f2-q10) are retrieved in the top 5 and answered; no question answered correctly or correctly declined in A2 gets worse; the D2 files publish or fail with a stated reason; spend stays under $1.

## Slices

| Slice | Content | Risk |
| --- | --- | --- |
| 0 | Baseline: table fill measurements (above) and the A2 retrieval results as the v4 reference (free, local) | Low |
| 1 | v5 chart regions (Part A); every skipped region on the real files checked against the rendered page | Medium |
| 2 | v5 captions, run-on headings and header rows (Part B) | Medium |
| 3 | Editor creates v5; upgrade notice text; docs | Low |
| 4 | Real-file round A3 and the "Extract v5" sheet (Part C), paid, under $1 | Low |

## Verification

As for spec 0008: unit tests per slice with synthetic PDFs; the frozen v1-v4 extractor tests unchanged; the seven real files extracted locally after Slices 1 and 2, compared block by block with v4 (`extract_baseline.py`); the full backend suite in the isolated stack; frontend lint, typecheck and tests with `--maxWorkers=1`; the editor checked in the browser at `http://127.0.0.1:5273`. Each slice is committed on local `main`; nothing is pushed until the owner asks.

## Out of scope

- Changing v1-v4 output.
- Chunking changes, including a DOCX heading kept with the text it introduces (the A2 DfT word-limit miss).
- OCR accuracy on old typewritten tables (needs another OCR engine).
- Non-English OCR (D1).
