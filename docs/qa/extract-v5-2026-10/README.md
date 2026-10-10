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
