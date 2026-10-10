# Extract v5 proof (spec 0009)

Spec: `docs/specs/0009-extract-v5-charts-and-table-context.md`. Files and licences: `files` and `files_v4` in `backend/scripts/real_source/sources.json`. The v4 reference output is `docs/qa/extract-v4-2026-10/raw/slice5-v4.json`.

## Slice 0: baseline (2026-10-10, local)

The table fill measurements are in the spec. The A2 retrieval and answer results (spec 0008, Slice 6) are the v4 reference for round A3.

## Slice 1: charts are not tables (2026-10-10)

`layout-ocr-v5` treats a detected table with under 30% of its cells filled as a chart region. Its text is read as ordinary layout blocks marked `chart_region: true`; it adds no table block and no malformed-table count. A table lying at least half inside a chart region (a legend box or figure label) is part of the chart too.

`raw/slice1-v5.json` is the seven test files extracted with `layout-ocr-v5` and the recommended settings:

| File | Blocks v4 → v5 | Tables v4 → v5 | Malformed v4 → v5 | Chart-region blocks |
| --- | --- | --- | --- | --- |
| F1 BERT paper | 465 → 471 | 19 → 14 | 0 → 0 | 11 |
| F2 Census P60-279 | 811 → 829 | 42 → 33 | 0 → 0 | 27 |
| F3 Surveyor VI scan | unchanged | 0 | 0 | 0 |
| F4 Eurostat (French) | 2,102 → 2,496 | 61 → 20 | **3 → 0** | 435 |
| F5 USGS scan | unchanged | 0 | 0 | 0 |
| F6 DfT DOCX | unchanged | 63 | 0 | 0 |
| F7 Prevent PPTX | unchanged | 3 | 0 | 0 |

- **Eurostat no longer fails the default policy.** Its malformed-table error is gone; the remaining findings are warnings (6 empty pages, mixed languages, suspicious reading order on 6 pages instead of 5). The chart callout "381 décès pour 100 000 habitants" (p. 21) is now in the text.
- **Every skipped region is a chart.** The 46 Eurostat and BERT regions were rendered side by side and checked by eye: bar, line and scatter charts, a map, illustrations, BERT's Figure 1 with its label boxes, and a learning curve. The 9 Census regions are on the pages of Figures 2, 3, 5, 6 and C-1, plus the cover's masthead box.
- **No text is lost.** Against each page's own text layer (`page.get_text()`), the characters a version fails to capture on native pages: Eurostat 1,655 in v4 and 215 in v5; BERT 136 and 134; Census 14,522 and 14,508. No page of the three files captures less in v5 than in v4. Comparing v5 with v4 directly shows up to 106 "missing" characters, but these are duplicates: v4's table extraction repeated chart labels across cells (up to 60 characters beyond the page's own text on one page).
- A first version left out chart blocks without a word (axis ticks, country codes). It was changed because chart data labels can be plain numbers (Census Figure 3's "-6.7", Eurostat bar values), and v4 kept those inside its table block.

Tests: `backend/tests/test_extract_v5_charts.py` (a 55-column synthetic chart beside a real table: v4 drops the callout and reports a malformed table; v5 reads all chart text, keeps the real table and reports none; no text v4 read is lost; the 30% threshold; the overlap share; v5 equals v4 on the corpus without charts; identity and website reading).

## Slice 2: tables keep their caption and header (2026-10-10)

`layout-ocr-v5` now also:

- attaches a caption such as "Table A-2. Households by …" to the table directly after it on the same page. The caption (its title, without the parenthesised note) becomes the last element of the heading path of the caption block and of every block of that table, and is stored in `table.caption`;
- replaces a notes or references heading ("Endnotes", "Notes", "References", "Sources" and French forms) that ran on from an earlier page with that caption. Other headings stay, because a section's table can sit pages after its heading: a first version that replaced any earlier-page heading dropped "Results"-style sections in a test and was narrowed;
- repeats all printed header lines (not just the first) in each row group of a table rebuilt as word rows. Header lines end at the first data line; currency column ranges ("$15,000") are header text, and a capitals section label ("ALL RACES") stays a body row.

`raw/slice2-v5.json`, the seven files with the finished Part A and Part B:

- **Census:** 30 of 33 tables carry their caption (Tables A-1 to A-7 including every continuation page, B-1 to B-4 and C-1). No table block sits under "Endnotes" any more (19 in Slice 1). Rebuilt tables repeat their full header: the Table A-2 rows for 2015 and 1990 now read under "… > APPENDIX A. ESTIMATES OF INCOME > Table A-2. Households by Total Money Income, Race, and Hispanic Origin of Householder: 1967 to 2022—Con.", after the header "… Median income (dollars) … Mean income (dollars) …". The text of every other block is unchanged; two pages gain one row group because the longer header fills a group sooner.
- **Not captioned:** a small figure fragment on p. 12, the CPI table on p. 20 (it has no "Table" caption) and Table A-4a on p. 39, where a column label ("Measures of income dispersion") is read between the caption and the table.
- **The other six files** are unchanged from Slice 1: none has a "Table …" caption directly above a detected table.
- The running page footer ("32 Income in the United States: 2022 …") is still classified as a heading on some appendix pages and can appear in a path before the caption. This predates v5 (spec 0008, Slice 3) and is not changed here.

Whether this makes the Table A-2 rows retrievable is measured in round A3 (Slice 4).

Tests: `backend/tests/test_extract_v5_table_context.py` (header lines on Census-like rows and edge cases, the caption pattern including `A-4a` and `TABLE 1`, notes headings, caption and run-on replacement, a section heading from an earlier page kept, a caption without a table left alone, only the first table takes a caption, and an end-to-end appendix PDF where v4 files the table under "Endnotes" and v5 under its caption with identical text).

## Slice 3: new drafts use v5 (2026-10-10)

The editor now creates `layout-ocr-v5`. Saved v1-v4 pipelines keep their extractor, show "upgrade available" on the Extract card and the **Saved with …** notice, which now also says v5 reads charts as text and files each table under its caption. The backend services were rebuilt so the API and workers accept v5.

Checked in the browser at `http://127.0.0.1:5273` on desktop and phone: a new draft shows no upgrade notice; the saved spec 0007 A1 pipeline (v3) and spec 0008 A2 pipeline (v4) show the notice and "upgrade available", and **Upgrade extraction** turns each into an unsaved v5 draft; no console errors.

Verification: the full backend suite in the isolated stack (662 passed, 5 skipped; the 3 known failures, unchanged); 386 Vitest tests, lint and typecheck; the docs site build and public check.

## Slice 4: real-source round A3 (2026-10-10, paid)

Round A3 ran through the public API with `backend/scripts/real_source/run.py`, in the spec 0006 project, with `layout-ocr-v5` and the recommended settings. Results are in `docs/qa/real-source-2026-10/raw/` (`state.json`, `structure.json`, `answers_A3.jsonl`, the A3 rows of `manual_scores.csv`) and the workbook's new **Extract v5** sheet.

Setup:

- **Spec 0006 files** (BERT, Census, Surveyor VI) under **Stop and let me review**, as in A1 and A2.
- **Spec 0008 files** (Eurostat, USGS scan, DfT DOCX, Prevent PPTX) now also under **Stop**; in A2 they needed "Publish the others" because Eurostat failed.
- **Spec 0009 files** (`files_v5` in `sources.json`, track "d2"): eight public files picked by the default in D2, because the owner did not name document types. They are a 2026 IRS Form W-4 (form with worksheet tables), NIST SP 800-63B (80-page technical standard, withdrawn in 2025 and kept for history), GAO-23-900494 (testimony with charts and a table), Executive Order 9066 page 1 (a typed 1942 scan at 500x776 pixels, turned into an image-only PDF), NISRA Labour Force Survey tables (XLSX, 27 sheets), an ECGD organisation chart with pay tables (PPTX), a DfE information-sharing agreement template (DOCX) and a CC BY PLOS ONE paper with figures. They use "Publish the other files and show warnings" so each file's outcome is visible.
- **Websites** reuse the A1 index; v5 keeps the website reader.
- **19 new questions** (`"round": "A3"`), written from the source files before the run: two per file and three with no answer in the source. All A2 file questions were asked again.
- Answers use the same pipeline (`google/gemini-2.5-flash`, top 5, temperature 0), scored by Claude with the spec 0004 rubric against the references, not blind.

Results:

| Measure | A2 (v4) | A3 (v5) |
| --- | --- | --- |
| Spec 0008 files under "Stop" | failed (Eurostat) | **published** |
| Hit@5 / Hit@1, spec 0006 and 0008 file questions | 27/33, 16/33 | 27/33, 16/33 |
| Answers correct or correctly declined, spec 0006 and 0008 file questions | 19/25 | 19/25 (no answer better or worse) |
| Spec 0009 files published | | 8 of 8 (844 chunks) |
| Answers correct or correctly declined, spec 0009 questions | | 18/19 |
| Spend | $0.020 | $0.033 ($0.028 answers, $0.004 embeddings as the app reports them) |

- **Part A works.** The Eurostat report publishes under the default "Stop" policy.
- **No regression.** Every earlier file question keeps its retrieval and its answer label. Census Table A-1 family households moved from rank 4 to 1; Eurostat road freight from rank 1 to 2.
- **The wider set of document types works.** All eight new files publish. 18 of 19 questions are answered correctly or correctly declined: the form's worksheet amounts, the standard's password rules, the testimony's headline figure, both scan questions, both spreadsheet values (sheets read as tables), the slide deck's name and pay-band table, both DOCX clauses, the paper's facts and all three unanswerable questions. The one miss (g3-q2) is GAO's mandates table: its row label and count land in different chunks.
- **The two retrieval targets are still not met.** The Census Table A-2 rows now carry their caption and full header (Part B), and the Eurostat "381 décès pour 100 000 habitants" callout is now in the index (Part A). Neither reaches the top 5, so both questions are still declined. The Table A-2 chunk is about 780 tokens of nearly pure numbers and ranks below Table A-1 and Figure 2. The callout is classified as a heading and becomes its own 36-token chunk, which ranks below the chart's title and axis chunks. Both are now chunking and retrieval questions; spec 0009 left chunking out of scope.
- **Eurostat chunks are smaller.** The median chunk is now 24 tokens (35 in A2), with 360 single short lines (327), because chart labels are now text.
- **The low-resolution scan reads poorly but answers.** EO 9066's OCR has many character errors ("Secretary of Wer", "Comendors"); the model still answered both questions correctly from it.
- The automatic phrase check under-counts some hits: g8-q1's rank-1 chunk says "Forty-one participants" (the reference phrase was "N = 41"), and Eurostat prose gives "76,7 %" and "22,4 %" where the chart callouts round to 77 % and 22 %.

Against the spec's done-when: Eurostat publishes under "Stop", no A2 result got worse, the D2 files publish, and spend is under $1. Not met: the Eurostat callout question (f4-q1) and the two Census Table A-2 questions (f2-q9, f2-q10) are still not retrieved and answered, although extraction now provides what they need.
