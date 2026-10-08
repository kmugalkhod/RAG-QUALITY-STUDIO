# Real-source ingestion test, 2026-10-09 (spec 0006)

Workbook: [`real-source-test.xlsx`](real-source-test.xlsx) (8 sheets: Summary, Sources, Runs, Structure, Retrieval, Answers, Settings verdict, Findings). Raw results are in [`raw/`](raw/); the harness is `backend/scripts/real_source/`.

## What was ingested

Four websites, fetched once by the product's Website connector (robots.txt honoured, 1 request per second per site): the Python tutorial (17 pages), 10 Wikipedia articles, 10 GOV.UK guidance pages and 10 MDN pages, 3,209 chunks in total. Three real PDFs: the BERT paper (two-column, 16 pages), the US Census report P60-279 (62 pages of text and tables) and 10 scanned pages of the 1967 Surveyor VI mission report (image-only). 54 questions were written from the sources before looking at the extracted output: 47 answerable, each with the exact phrase the right chunk must contain, and 7 unanswerable.

## Rounds and results

| Round | Change | Websites Hit@5 | Files Hit@5 | Result |
| --- | --- | --- | --- | --- |
| R1 | Recommended settings | 25/28 (89%) | blocked | Files run failed: the Census report was flagged for malformed tables |
| R1w | Files: publish others with warnings | (R1) | 17/19 (89%) | Files baseline for R2-R4 and R6 |
| R2 | Extractor v1 | (R1) | 16/19 | v1 lost one scan question |
| R3a | OCR 300 DPI, 100 pages | (R1) | 17/19 | No change |
| R3b | OCR off | (R1) | blocked | The scan had no text and failed the whole run |
| R4 | Table evidence plain text | (R1) | 17/19 | No change |
| R5 | Websites: publish others | 25/28 | (R1w) | No change; no page failed |
| R6 | Chunks 300/400/40 | 26/28 | 16/19 | Hit@1 up (26 vs 24 overall), Hit@5 mixed; twice the chunks |

20 questions were also answered end to end (Gemini 2.5 Flash, top 5) and scored blind against the spec 0004 rubric: websites 10 correct and 2 correctly declined of 12; files 6 correct, 1 correctly declined and 1 wrongly declined of 8, identical for v1 and v2. Every correct answer was supported by the chunk it cited.

## Settings verdict

- **Keep visible:** "If a file can't be read well" (but fix what "publish the others" does), OCR languages, chunk size.
- **Keep in Advanced:** extractor version (upgrade only), maximum OCR pages (raise to 100), quality thresholds, language policy.
- **Candidate to remove:** the OCR on/off switch (always on), OCR resolution, per-page timeout, rotation and deskew, extraction strategy, table evidence. None changed a result on real content.

## Findings to fix first

- **X1** The recommended setting blocks an ordinary government report.
- **X2** Borderless PDF tables merge whole columns into one cell and cut cells at 1,000 characters, so report table values cannot be matched to their rows.
- **X3** "Publish the other files and show warnings" does not publish the others when a file cannot be read.

Also: website tables are flattened to one value per line (X4), line-break de-hyphenation merges real hyphenated words (X5), Wikipedia references can outrank the lead (X6), run details list out-of-scope links as succeeded (X7), and embedding cost is not recorded (X8).

## Cost and limits

Total about $0.20 of the $1 cap: embeddings about $0.17 as an upper-bound estimate from indexed bytes (the app does not record embedding cost), answers $0.015 as recorded. The workbook's Summary uses formulas set to recalculate when opened; they were cross-checked against the sheet data in Python because LibreOffice is not installed here. Answer labels are Claude's blind judgement and need the owner's spot-check of 10 rows. Sources are English only, and the scan is upright and clean, so OCR language and rotation were not stressed.

During the run, two retrieval passes (R1, R1w) were lost because a parallel stage overwrote the harness state file; both were rerun with identical settings before scoring.
