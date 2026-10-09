# 0007. Fixes from the real-source test (X1-X8)

**Date**: 2026-10-10
**Status**: Approved by the owner on 2026-10-10 ("fix all problem"), with three decisions: "Publish the other files and show warnings" skips unreadable files and pages and publishes the rest; new pipelines start with "Stop and let me review" for files and "Publish the others" for websites; output changes ship as a new extractor version, `layout-ocr-v3`.

## Summary

Spec 0006 ingested four real websites and three real PDFs and found eight problems (`docs/qa/real-source-2026-10/`). This spec fixes all eight and re-runs the same test to prove it.

| ID | Problem | Fix |
| --- | --- | --- |
| X1 | The recommended setting blocks an ordinary government report | X2 removes the cause; a rebuilt merged-column table is not a malformed table |
| X2 | Borderless PDF tables merge whole columns into one cell and cut cells at 1,000 characters | v3 detects merged-column tables and rebuilds one text row per printed line from word positions |
| X3 | "Publish the other files and show warnings" does not publish the others when a file or page cannot be read | Under that choice, any unreadable file or page is excluded with its reason and the index publishes with the rest |
| X4 | Website tables are flattened to one value per line | v3 website reading keeps each HTML table as rows with a header, split like PDF tables |
| X5 | Line-break de-hyphenation merges real hyphenated words | A new de-hyphenation mode keeps the hyphen when the same hyphenated word appears elsewhere in the document |
| X6 | Reference lists and notes outrank facts on long pages | v3 website reading leaves out reference lists, footnote lists and inline citation markers |
| X7 | Run details list out-of-scope links as succeeded with 0 chunks, often twice | Out-of-scope links are listed once as skipped, with the reason |
| X8 | Embedding cost is not recorded | Each run records the provider's embedding token usage and cost, shown in run details |

## Versioning (decision 3)

- `layout-ocr-v3` is added to `ExtractNodeV2.config_version`. It includes everything in v2 plus X2, X4 and X6. `layout-ocr-v1` and `layout-ocr-v2` keep their exact output; the v1 digests and the v2 corpus test must keep passing unchanged.
- v3 applies to website pages as well as files: the website extractor version recorded in a run's processing identity changes only for v3, so a saved v2 website pipeline keeps its output and reuses its stored revisions.
- New drafts use v3. A saved v1 or v2 Extract node shows the existing **Upgrade extraction** callout for every source kind (it was hidden for page-only pipelines in spec 0004 slice 7, because v2 changed nothing for websites; v3 does).
- X5 adds a de-hyphenation mode `conservative-compounds`. New cleaning profiles use it; saved steps keep `conservative`.
- X3 and X7 change run handling and reporting, not extracted content, so they apply to every version. X8 adds fields; it changes no existing value.

## Requirements

### Slice 1: v3 and merged-column PDF tables (X2, X1)

1. `layout-ocr-v3` passes the same schema rules as v2 and has its own extractor version string, so its processing identity differs from v2.
2. For v3, a detected PDF table is a **merged-column table** when at least two of its cells each hold five or more text lines and the table has fewer rows than its fullest cell has lines. Ordinary tables, including the 40-row corpus table and tables with short wrapped cells, are not affected.
3. A merged-column table is rebuilt from the page's words inside the table area: words are grouped into printed lines by their vertical centre, ordered left to right, and runs of dot leaders are collapsed. The result is one `table` block whose text has one line per printed row, with attributes recording `reconstruction: "word-rows"` and the row count. It is split into row groups within the attribute budget like any v2 table, with the first line repeated.
4. A rebuilt table is not counted as malformed. Only a table cut by the existing safety limits is.
5. On the Census report under v3 and the recommended policy, the document passes (or warns) instead of failing, and "Married-couple" and "110,800" appear on the same line.

### Slice 2: "Publish the others" really publishes the others; per-source defaults (X3)

1. When the saved quality policy's `failed_item_action` is `exclude` ("Publish the other files and show warnings"), every file or page whose processing fails, for any reason, is marked `excluded` with its reason, and the run publishes the remaining items. This applies to uploaded files, S3, Notion, Confluence and websites, and to merged and per-source layouts.
2. The run still fails, and the previous index stays current, when no item is left to publish, or when the run fails for a reason outside item processing (cancellation, embedding failure, a source that cannot be reached at all).
3. Under `fail` ("Stop and let me review"), behaviour is unchanged.
4. The run summary counts excluded items, and each excluded item shows the plain reason.
5. In the editor, new pipelines and **Reset to recommended** use "Stop and let me review" when any source reads files (uploads, S3) and "Publish the others and show warnings" when every source is a website, Notion or Confluence. The plain explanation under the choice says what happens to an unreadable file or page.

### Slice 3: v3 website reading (X4, X6)

1. For v3, each HTML `<table>` becomes one `table` block in reading order: rows from `<tr>`, cells from `<th>`/`<td>` (nested tables flattened into their cell's text), the first row as the header, rendered as Markdown and split into header-repeating groups like PDF tables. Infobox-style two-column tables become `label | value` rows.
2. For v3, content inside reference and note lists is left out: elements with the classes `reflist`, `references`, `mw-references-wrap` or `navbox`, inline citation markers (`sup.reference`), and sections whose heading is References, Notes, Explanatory notes, Footnotes, Citations, Sources, Bibliography, Further reading or External links, up to the next heading of the same or a higher level.
3. Without v3, website reading is byte-for-byte unchanged.

### Slice 4: compound-aware de-hyphenation (X5)

1. The `dehyphenate` step accepts `mode: "conservative-compounds"`. It joins a word split by a line-break hyphen as `conservative` does, except when the hyphenated form (for example `married-couple`) also appears elsewhere in the same document, case-insensitively; then the hyphen is kept and the line break removed.
2. The default structure-aware cleaning profile used by new drafts uses the new mode. Saved pipelines keep their saved mode.

### Slice 5: out-of-scope links in run details (X7)

1. A website link that was discovered but falls outside the source's scope (origin, path prefixes, depth or page limit) appears once in the run's items, as `skipped` with the reason, never as succeeded.
2. Items are de-duplicated by canonical URL within a source.

### Slice 6: embedding usage and cost (X8)

1. The embedding adapter returns the provider's reported token usage and, when the provider reports it, the cost.
2. Each ingestion run stores embedding tokens and embedding cost (nullable: unknown is not zero), through a migration. Re-used stored chunks add nothing.
3. The run read API and the run details panel show them, labelled as provider-reported; an unknown cost shows as unknown.

### Slice 7: re-run the real-source test

Re-run spec 0006 R1 (recommended settings, now v3 and the per-source defaults) on the same website snapshot and files, plus R1w for comparison, with the same 54 questions and the same scoring. Add an "After fixes" section to the workbook and README.

**Done when:** the recommended files run publishes; Census table questions f2-q4 and f2-q5 retrieve their row; website table and reference findings are gone from the sampled chunks; no answerable question that passed before fails now; embedding cost is recorded by the app.

## Verification

Each slice has unit tests (and PostgreSQL integration tests for run handling and the migration), keeps the v1 golden digests and the v2 corpus test unchanged, and passes the full backend suite in the isolated stack (the three failures that predate this work are listed separately) and the frontend suite. Slices 2 and 6 change the UI and are checked in the browser at `http://127.0.0.1:5273` when memory allows. Each slice is committed separately on local `main`; nothing is pushed until the owner asks.

## Out of scope

- PPTX table extraction.
- Changing v1 or v2 output.
- Removing Extract settings; the settings verdict from spec 0006 is a separate spec.
