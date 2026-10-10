# Extract v4 proof (spec 0008)

Spec: `docs/specs/0008-simpler-extract-and-v4.md`. Files and licences: `files` and `files_v4` in `backend/scripts/real_source/sources.json`. The files themselves are not in the repository; each entry has its download URL and SHA-256.

## Slice 0: v3 baseline (2026-10-10, local, no provider cost)

`backend/scripts/real_source/extract_baseline.py extract WORK layout-ocr-v3 OUT` ran `extract_document` on seven files with the recommended Extract settings (Auto strategy, OCR auto in English, Preserve tables, default quality policy, Maximum OCR pages 100). Every block, page origin and finding is in `raw/baseline-v3.json`.

| File | Blocks | Tables | Pages (origin) | Quality | Notes |
| --- | --- | --- | --- | --- | --- |
| F1 BERT paper | 465 | 19 | 16 layout | warn | 1 suspicious reading order, as in spec 0007 |
| F2 Census P60-279 | 910 | 44 | 62 layout | warn | Rotated tables transposed (below) |
| F3 Surveyor VI scan | 74 | 0 | 10 OCR | pass | OCR confidence median 96.5 |
| F4 Eurostat key figures 2019 (French) | 2,102 | 61 | 69 layout, 6 OCR, 1 native | **fail** | 3 malformed tables (error), 6 empty pages, mixed languages |
| F5 USGS Circular 115 scan (1951) | 157 | 0 | 16 OCR | warn | OCR confidence median 95.9, p05 88.3; 3 empty pages |
| F6 DfT highways template (DOCX) | 193 | 63 | none | pass | Tables read |
| F7 Prevent risk assessment (PPTX) | 22 | **0** | 14 native | pass | Table text missing (below) |

What the baseline shows for each spec 0008 gap:

- **B1 rotated tables.** Census pp. 22-23 (and the other rotated pages) come out as a three-column table whose cells hold whole printed columns, for example `| Mean income (dollars) | Margin of error1 (±) | 1,034 1,110 1,183 ... |`. Years and values are not on the same row.
- **B2 PPTX tables.** None of the slide-table phrases are in the output: "Almost certain", "Very likely", "Catastrophic", "7 to 11", "Medium risk", "Severity x Likelihood" (slides 12-13). The three `a:tbl` frames are skipped.
- **B3 hyphen remainder.** v3 extraction contains no "marriedcouple" and no "married-" line break; all four "Married-couple" occurrences keep their hyphen. Census p. 8 has a soft hyphen at a line end (`house\xad\nholds`). So the remaining merge is not in v3 extraction; Slice 5 traces it through cleaning (`conservative-compounds`).
- **B4 scans.** F5 tables on pp. 8-9 come out as one row per state with character errors ("Neveda", "Wew Jersey", "6,40D"); pp. 10-14 are maps with little text, which is correct. Slice 5 measures the character error rate against a hand-checked page.
- **New: F4 fails the default policy.** The French Eurostat report is blocked by three malformed tables (error) and has six near-empty pages sent to OCR. This matters for round A2: under "Stop" it would block the files run. Slice 5 records the cause before anything is changed.

Limits:

- The backend image has only the English OCR pack (`eng`, `osd`). F4 is native French text, so it tests non-English extraction and language detection, not non-English OCR. A non-English scan needs a Tesseract language pack, which changes the image and is out of scope for spec 0008 unless the owner approves it.
- F5 was not visibly skewed: the app's deskew angle is 0 on 14 of 16 pages and −0.5° on one (−3° on the two cover pages is the edge of the search range). It is a low-quality scan, not a skewed one; D4 allows either.
- F5 is an image-only copy made locally: each page's scan image placed unchanged on a new page, without the publisher's hidden OCR text layer. Its bytes may differ between PyMuPDF builds; `source_sha256` checks the original download.

## Slice 3: sideways pages in `layout-ocr-v4` (2026-10-10)

Census P60-279 prints its appendix tables (Tables A-2 to A-5, pp. 22-36 and 42-44) on portrait pages with the text turned 90 degrees: every line reads bottom to top, and the PDF's page rotation is 0. v4 measures the direction of each page's text; when at least 60% of at least 100 characters run sideways, it reads a straightened one-page copy with the v3 layout and table code, then maps every block box back onto the original page and records the turn in the page's `rotation_degrees`. Upright pages take the unchanged v3 path.

`raw/slice3-v4.json` is the same seven files extracted with `layout-ocr-v4`:

- Six files are block for block identical to v3. Census changes only on pp. 22-36 and 42-44 (910 to 811 blocks).
- Every sideways table is rebuilt as one line per printed row, header first, for example `2022 131,400 100 8.3 7.4 7.6 10.6 16.2 12.3 16.4 9.2 11.9 74,580 968 106,400 1,034` (Table A-2) and `2022 3.5 9.1 14.6 22.1 50.7 10.37 2.71 3.82 0.467 ...` (Table A-5). Pages 22-35 have 10 to 35 year rows each; p. 36 is the footnotes page and is now read in order.
- The set of headings is the same as v3. The running footer ("36 Income in the United States: 2022") is classified as a heading in both versions; that predates v4 and is recorded here as a separate finding, not fixed in this slice.
- Footnote markers stay attached to the year as in v3 (`20202` is 2020 with note 2).

Not covered: a sideways table region on an otherwise upright page (none of the test files has one), and pages that set a PDF page rotation as well as sideways text; both keep the v3 reading.

## Slice 4: PowerPoint tables in `layout-ocr-v4` (2026-10-10)

v3 reads only a slide's text shapes (`p:sp`), so tables in table frames (`p:graphicFrame` holding `a:tbl`) were dropped. v4 (format reader `formats-v3`) walks each slide in document order and reads every table frame as header-repeating table blocks through the same row-group code as DOCX tables, with the slide number, table ID (`s13-t2`) and header row. A merged cell's continuation stays an empty cell so columns stay aligned. Text shapes keep their v3 blocks and shape numbers.

`raw/slice4-v4.json`, all seven files with `layout-ocr-v4`:

- F7 (Prevent slides) goes from 22 to 25 blocks: its 22 text blocks are unchanged and its three tables are added (table count 0 to 3, quality pass). Every phrase that was missing in the baseline is now present: "Almost certain", "Very likely", "Catastrophic", "7 to 11", "Medium risk", "Severity x Likelihood".
- The other six files are block for block identical to Slice 3.
- A table without a header row, such as slide 13's "Low risk | 1 to 6", has its first row treated as the header, as for DOCX tables.

## Slice 5: hyphens, scans and the Eurostat failure (2026-10-10)

### B3: the remaining "married-couple" merge

The merge was not in the cleaner. Spec 0007's A1 files pipeline (version `6fe0c1ad`) was saved with dehyphenate mode `conservative`, because the harness (`run.py`) built pipelines from a copy of `ingestion-capabilities` saved at setup, before spec 0007 made `conservative-compounds` the default. A1 never ran the compound-aware mode. Running today's default cleaning steps on the Census extraction keeps the hyphen in all five "married-couple" forms, including the one broken across lines on p. 8. The harness now reads the capabilities again before it creates each pipeline, so round A2 uses the server's current defaults.

Tracing p. 8 step by step found a larger defect. Census marks its line-break hyphens with a soft hyphen (U+00AD): `house­\nholds`. `remove_control_characters` deletes U+00AD, then `reflow_pdf_lines` turns the line break into a space, so every such word is split in two after cleaning ("house holds", "dedi cation", "household ers"). The cause is in extraction: the text layer passes the typesetter's hyphen through unchanged. `layout-ocr-v4` now rejoins a word at a soft hyphen followed by a line break, outside tables; a soft hyphen inside a line is left for cleaning, which removes it. v1 to v3 and every cleaning mode are unchanged.

`raw/slice5-v4.json`, all seven files with `layout-ocr-v4`: Census changes only in 63 paragraph and footnote blocks, where 118 words are rejoined and nothing else differs; the other six files are identical to Slice 4. No soft-hyphen line break remains outside tables. The 17 soft hyphens inside Census table cells stay as extracted (for example `(thou­ sands)` in a header, where the two halves are separate cell lines); cleaning removes the character and leaves a space, as in v3.

### B4: scan accuracy

Character error rate (CER) against hand-checked text in `ocr-truth/`, measured with `backend/scripts/real_source/ocr_cer.py`: each checked passage or row is aligned to the best-matching stretch of the page's OCR text, whitespace is collapsed and every other difference counts.

| Page | Checked text | CER at 200 DPI (recommended) | CER at 300 DPI |
| --- | --- | --- | --- |
| F5 USGS Circular 115 p. 5 (1951 typescript, prose) | 3 paragraphs, 1,009 characters | 0.20% | 0.40% |
| F3 Surveyor VI p. 5 (1968 print, prose) | whole page, 1,593 characters | 0.31% | 0.31% |
| F5 USGS Circular 115 p. 8 (typescript table) | 26 state rows, 1,203 characters | 3.33%; 224 of 234 values exact | 4.57%; 219 of 234 |

Prose scans read almost exactly; no fix is needed. The typescript table is where OCR misreads: single digits (65 read as 66, 75 as 78, 70 as 79), footnote markers (`4/` read as `ss` or `V`), column rules read as `|`, and the District of Columbia row's three zeros lost to specks. A higher resolution makes it worse, so the recommended 200 DPI stays. Improving it would need a different OCR engine or image clean-up, which is out of scope for spec 0008; the result is recorded as a known limit. A question that needs an exact number from an old typewritten table can get a wrong digit.

Not measured: a skewed scan (F5 is not skewed; see Slice 0) and a non-English scan (only the English OCR pack is installed).

### F4: why the Eurostat report fails the default policy

- **Malformed tables (error).** The three are charts, not tables. On pp. 21, 58 and 66 the table finder takes a chart's gridlines (one per country) as a table of 52 to 57 columns, of which 1 to 10 hold any text, so the table goes over the 50-column limit and is reported as malformed. Under **Stop and let me review** this blocks the whole file.
- **Six empty pages (warning).** Pages 12, 32, 54, 72, 74 and 75 have no text, no images and at most one drawing; they are blank pages, and OCR correctly finds nothing.
- **Mixed languages (warning)** was not traced further; it is a warning and does not block the file.

Nothing was changed for F4 in this slice. A possible v4 fix, for the owner to decide: treat a detected table whose cells are almost all empty as not a table, so its text is read as ordinary blocks and it is not counted as malformed.

## Slice 6: real-source round A2 (2026-10-10, paid)

Round A2 ran through the public API with `backend/scripts/real_source/run.py` in the spec 0006 project. Results are in `docs/qa/real-source-2026-10/raw/` (`state.json`, `structure.json`, `answers_A2.jsonl`, A2 rows of `manual_scores.csv`) and the workbook's new **Extract v4** sheet (`docs/qa/real-source-2026-10/real-source-test.xlsx`).

Setup:

- **Spec 0006 files** (BERT, Census, Surveyor VI): extractor `layout-ocr-v4`, Maximum OCR pages 100, other Extract settings recommended, **Stop and let me review**. This is A1 with only the extractor and page limit changed.
- **New files** (Eurostat, USGS scan, DfT DOCX, Prevent PPTX): a separate track and index with the same settings except **Publish the other files and show warnings**, because the Eurostat report is known to fail "Stop" (Slice 5).
- **Websites** reuse the A1 index: v4 keeps the website reader (`html-main-v3.1`), so a new website run would only re-embed the same text. Website retrieval in A2 is identical to A1; website questions were not asked again.
- **17 new questions** (`"round": "A2"` in `questions.jsonl`): 2 on the sideways Census Table A-2, 5 Eurostat (in French), 4 USGS, 2 DfT, 4 Prevent, of which 3 have no answer in the source. They were written from the source pages (rendered pages and the DOCX/PPTX XML), not from the app's output. Their reference phrases were fixed before the run, and they are not blind to the extractor, which had already been inspected in Slices 0-5.
- Answers use the spec 0006 answer pipeline (`google/gemini-2.5-flash`, top 5, temperature 0). They were scored by Claude with the spec 0004 rubric against the references, not blind, as for A1.

Results:

| Measure | A1 (v3) | A2 (v4) |
| --- | --- | --- |
| Spec 0006 files run under "Stop" | published | published (637 chunks) |
| Hit@1 / Hit@5, spec 0006 file questions | 9/19, 19/19 | 10/19, 19/19 |
| Answers correct or correctly declined, spec 0006 file questions | 8/8 | 8/8 |
| New files run ("Publish the others") | not run | published, all 4 files (1,030 chunks) |
| Answers correct or correctly declined, new questions | n/a | 11/17 |
| Spend | | $0.020 ($0.017 answers, $0.003 embeddings as the app reports them) |

- **No A1 result got worse.** Every spec 0006 file question is still found in the top 5, and all 8 asked file questions are still answered correctly or correctly declined. The Table A-1 married-couple question improved from rank 2 to rank 1. Website retrieval is identical.
- **PowerPoint tables work.** All three Prevent table questions are found (ranks 1, 1, 3) and answered correctly from the slide tables. In A1 that text was not in the index at all.
- **DOCX tables work** (f6-q2, rank 1, correct).
- **Sideways Census tables are read correctly but not found.** The Table A-2 rows for 2015 and 1990 are in the index exactly as printed, row by row. Neither ranks in the top 5, so the model correctly declines with the evidence it got. The rows are pure numbers, and the chunk's section path is "Endnotes": a heading on p. 20 runs on over the whole appendix, while the caption "Table A-2." is read as a paragraph, not a heading. The multi-line column header is not repeated per row group. All three causes predate v4 (A1's Table A-1 sits under "Endnotes" too). Changing heading or chunk context would change v4's output after A2 saved v4 pipelines, so it is recorded for a later version, not changed here.
- **Eurostat chart callouts are lost.** "381 décès pour 100 000 habitants" (p. 21) is not in the index: the chart is read as an almost empty 53-column table, and text inside its box is dropped. Prose questions are answered (f4-q2, f4-q3), and f4-q4 is answered correctly from the prose figure "22,4 %". The report is split into 899 chunks with a median of 35 tokens, 327 of them single short lines, so retrieval works on fragments. This supports the chart-as-table fix proposed in Slice 5.
- **The USGS typewritten table is hard to retrieve.** The Illinois row is in the index but outside the top 5. Kansas's 75 is misread as 78 (the B4 limit); the automatic rank-2 hit for f5-q3 is a false match on "750" in another row. Prose (f5-q1) is found at rank 1 and answered.
- **DfT word limit (f6-q1) declined.** The rank-1 chunk holds "Word limit – 250 words", but the "A3.2" heading sits in an earlier chunk, so the model could not tie the limit to A3.2. This is a chunking limit, not an extraction one.
- **All three unanswerable questions were correctly declined.**

Against the spec's done-when: the Extract panel, unchanged saved pipelines, no A1 regression, the scan measurements and the spend all hold. PowerPoint tables answer their questions. The rotated Census tables are extracted correctly but do not yet answer their questions, because of the retrieval context described above.
