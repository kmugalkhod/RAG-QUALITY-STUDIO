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
