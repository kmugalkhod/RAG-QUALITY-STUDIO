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
