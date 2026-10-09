# 0008. Simpler Extract settings and extractor v4

**Date**: 2026-10-10
**Status**: Approved 2026-10-10. The owner accepted the recommendation for D1-D4. Implementation starts with Slice 0.

## Summary

After spec 0007 the Extract node rates about 8/10: 9 for safety and provenance, 7.5 for extraction quality, 6.5 for ease of use. Two things hold it back:

1. **Too many settings.** The real-source test (spec 0006, `docs/qa/real-source-2026-10/`) changed each Extract setting on real websites and PDFs. OCR resolution, per-page timeout, rotation and deskew, extraction strategy and table format never changed a result, and turning OCR off only broke scans. They still sit in the panel.
2. **Known extraction gaps.** Rotated landscape tables come out transposed (Census P60-279, pp. 22-34). One of five "married-couple" line breaks still merges. PowerPoint tables are not read at all. Skewed and non-English scans have not been tested.

This spec removes the settings that do nothing for users, fixes the gaps in a new extractor version `layout-ocr-v4`, and proves both on a wider set of real files.

## Decisions for the owner

| ID | Decision | Recommendation (approved 2026-10-10) |
| --- | --- | --- |
| D1 | What happens to the removed settings | Remove them from the panel only. The schema keeps the fields, new drafts get the recommended values, and saved pipelines run exactly as saved. A saved pipeline whose value differs shows one line: "Uses an older custom setting: OCR resolution 300 DPI. Reset to recommended." |
| D2 | Maximum OCR pages | Default 100 (from 50) and keep it in Advanced. A longer scan costs only local CPU time, not provider money. |
| D3 | Output changes | New version `layout-ocr-v4`. v1, v2 and v3 keep their exact output; saved pipelines see the existing "upgrade available" notice. |
| D4 | Test files for the proof | Public files with a clear licence: one non-English government PDF, one skewed or low-quality scan, one DOCX and one PPTX with tables, plus the three spec 0006 PDFs. The spending cap is again $1. |

## Part A: simpler settings (UI only; no output change)

The Extract panel after this part:

| Where | Settings |
| --- | --- |
| Visible | "If a file can't be read well" (Stop / Publish the others), OCR languages, the upgrade notice |
| Advanced | Maximum OCR pages, quality thresholds, language policy |
| Removed from the panel (fixed to the recommended value) | OCR on/off (on), OCR resolution (200 DPI), per-page timeout (30 s), rotate pages (on), deskew (on), extraction strategy (Auto), table format (Preserve) |

Requirements:

- A1. New drafts, guided setup and "Reset to recommended" produce the recommended values for every removed field. `recommendedExtractSettings` in `frontend/src/features/ingestion-pipelines/editorModel.ts` stays the single source of these values.
- A2. A saved node with a non-recommended removed value keeps that value when it is saved again. The panel names it, plain and read-only, with a reset button (D1). The node is never silently changed.
- A3. The "N settings differ from recommended" summary counts only settings the user can still see, plus the read-only legacy line.
- A4. The backend keeps accepting all current fields. The API still rejects invalid values, and saved versions still validate. No migration.
- A5. Website-only pipelines show no OCR settings at all, as today.
- A6. Docs: `docs/site/docs/ingestion/extraction.md` describes the shorter panel; screenshots that show removed controls are refreshed.

Files: `components/IngestionNodeSettings.tsx` (Advanced section around line 983 onward; strategy, OCR and table controls about lines 1020-1190), `editorModel.ts` (lines 81, 240-247), `guidedModel.ts`, and the tests under `frontend/tests/features/ingestion-pipelines/`.

## Part B: extractor `layout-ocr-v4`

- B1. **Rotated tables.** On a page or table region whose text runs at 90 or 270 degrees, rebuild rows in reading order from word positions, using the same method as v3's merged-column rebuild. The Census rotated tables must read header first, one row per printed line. Code: `backend/app/ingestion_content/extractors/pdf.py` (`_is_merged_column_table`, `_word_rows` around lines 741-760, and the page rotation code around lines 937-1060).
- B2. **PPTX tables.** `_pptx_segments` in `extractors/formats.py` (line 502) reads only text shapes (`p:sp`). v4 also reads table frames (`a:tbl` inside `p:graphicFrame`) as header-repeating table blocks through `table_row_groups`, recording the slide number.
- B3. **Remaining hyphen merge.** Trace why one Census "married-\ncouple" still becomes "marriedcouple" under `conservative-compounds` (the line break may be removed during extraction, or the hyphen may be a soft hyphen) and fix it at the cause. If the fix is in cleaning rather than extraction, it ships as a new cleaning mode, so existing cleaning output does not change.
- B4. **Scans.** Measure, without changing them, how skewed and non-English scans come out (character error rate against a hand-checked page). Fix only what the measurement shows; record a result that needs no fix as such.

Rules: v1, v2 and v3 output stays byte-identical (v1 golden digests, the v2 corpus test and the v3 table tests unchanged). New drafts use v4. The website reader keeps `html-main-v3.1` unless a v4 change needs it.

## Part C: proof

- C1. Re-run the real-source harness (`backend/scripts/real_source/run.py`) as round A2 with v4 and the simplified defaults, on the spec 0006 sources plus the D4 files, with new questions written from the new files before looking at the output.
- C2. Add the results to the workbook as an "Extract v4" sheet, with the same before-and-after style as "After fixes".

**Done when:** the Extract panel shows only the settings in the table above; saved pipelines run unchanged; rotated Census tables and PPTX tables answer their questions; no question that passed in A1 fails; the scan measurements are recorded; spend stays under $1.

## Slices

| Slice | Content | Risk |
| --- | --- | --- |
| 0 | Baseline: v3 output for the corpus, the Census rotated pages and the new D4 files (free, local) | Low |
| 1 | Part A UI: shorter panel, legacy line, reset, tests | Low |
| 2 | Part A docs and screenshots; Maximum OCR pages default 100 | Low |
| 3 | v4 rotated tables (B1) | Medium |
| 4 | v4 PPTX tables (B2) | Low |
| 5 | Hyphen remainder (B3) and scan measurements (B4) | Medium |
| 6 | Real-source round A2 and workbook (Part C), paid, under $1 | Low |

## Verification

Same rules as spec 0007: unit tests per slice; PostgreSQL tests where run handling or persistence is touched; full backend suite in the isolated stack (three failures predate this work: `test_connections` tamper 403, `test_existing_files` OCR-pack, the redis celery test); frontend lint, typecheck and tests with `--maxWorkers=1` (low memory). UI slices are checked in the browser at `http://127.0.0.1:5273`. Each slice is committed on local `main`; nothing is pushed until the owner asks.

## Out of scope

- Changing v1, v2 or v3 output.
- Removing schema fields or migrating saved pipelines.
- New OCR engines or the `pymupdf_layout` package (needs separate licence and image-size approval).
- Chunking and retrieval ranking changes (Hit@1 for files is partly a chunking question).
