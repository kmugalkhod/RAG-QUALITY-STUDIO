# 0014. Table rows that are kept and can be found

**Date**: 2026-10-18
**Status**: Approved 2026-10-18 ("go ahead with the table fixes"); recommendations D1-D7 taken as accepted. Slice 0 passed (`docs/qa/table-rows-2026-10/README.md`): with the new versions g3-q2 is rank 1 and f2-q10 rank 2 by vector search, f2-q9 rank 3 by hybrid search, and no vector top-5 hit is lost.

## Summary

Spec 0013 Slice 0 showed that the remaining wrong table answers are not a search problem:

- **GAO-23-900494, Table 2 (g3-q2, "Inhofe … 158").** The row is not in the index at all. PyMuPDF finds the table as two small ruled "tables", the header and the Total row, and the rows between them are ordinary text blocks. `layout-ocr-v5` drops every text block that touches a table box. On page 5 the Inhofe row starts 0.00001 points inside the header box, and on page 2 the "158 | 312" block overlaps it by 0.7 points, so both copies of the row are dropped, while the other rows survive as loose paragraphs.
- **Census P60-279, Table A-2 (f2-q9 "2015 … 68,410", f2-q10 "1990 … 76,820").** The rows are extracted, but:
  - The table's columns are lost. v5 rebuilds this borderless sideways table from word rows as one text line per printed row ("2015 125,800 100 9.1 … 68,410 639 95,950 802"). Its five stacked header lines run together ("Hispanic Race origin and of Percent distribution Median (dollars) income …"), so nothing says which number is the median.
  - Every passage holds a dozen look-alike year rows, and 15 pages repeat the same layout for other race groups. Only the first row of each group carries its label ("ALL RACES"). Spec 0010 tried smaller table passages (about 200 tokens) and still could not find the 2015 row.

This spec makes two changes:

- **The extractor keeps those rows and labels each column** (new extractor version `layout-ocr-v6`).
- **The chunker gives each table row its own passage.** The passage carries the table caption, the column names and its group label, and is searched as "column: value" text (new chunking versions `section-token-v4` and `parent-child-v4`).

Saved pipelines keep running exactly as saved: v1-v5 extraction and v1-v3 chunking are unchanged.

## Decisions (recommendations taken as accepted 2026-10-18)

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | Where the fixes go | **A new extractor version, `layout-ocr-v6`**, for kept lines and labelled columns, and **new chunking versions, `section-token-v4` and `parent-child-v4`**, for row passages. Earlier versions stay frozen and byte-identical. |
| D2 | Which text near a table is dropped | **A text line, not a whole block, is dropped**, and only when at least half of its area lies inside a detected table box. Lines outside every table are kept, in reading order. |
| D3 | How a word-row table gets its columns | **From the data lines:** the right edges of numbers on lines that are mostly numbers mark the columns. Text left of the first column is the row label. Each header word goes to the column its centre falls in, and the words are read top to bottom; a word split with a hyphen is joined ("(thou-" + "sands)"). If fewer than three data lines agree on the columns, the table falls back to v5's one-line-per-row text. |
| D4 | Group labels inside a table | **A row with text only in its first cell ("ALL RACES", "WHITE ALONE") is a group label.** It stays a row of the table, and the rows below it carry it in their passages until the next label. |
| D5 | Table passages | In the v4 chunkers each body row of a structured table becomes its own passage. Its text is the header (when it fits the passage limit; a `parent-child-v4` child usually leaves it to its parent), the row's group label and the row. Its searched text is the section path followed by "column: value" pairs. In `parent-child-v4` the rows are the children and the parent is built exactly as in v3. Prose, and tables without a structured row copy, are chunked exactly as in v3. |
| D6 | Default for new pipelines | **`layout-ocr-v6` with v4 chunking**, but only if the proof round (Slice 5) loses no correct answer and no top-5 hit against round A5, and finds g3-q2 and at least one of f2-q9 or f2-q10 in the top 5. Otherwise new pipelines stay on v5 with v3 chunking, and the new versions remain a choice. |
| D7 | Spending | Slice 0 pays for embeddings only (under $0.05). The proof round pays for embeddings and about 150 answers (about $0.20). The cap is $1. |

## Part A: extraction, `layout-ocr-v6`

- **A1. Kept lines (D2).** `_layout_page` filters each text block line by line: a line whose box lies at least half inside a table box is dropped, and the remaining lines of the block form the block. Expected effect on GAO Table 2: both copies of the Inhofe row are kept. Page 5's rows stay under the "Table 2: …" caption heading, as the other rows already do.
- **A2. Labelled columns (D3, D4).** When v3-v5 would rebuild a merged-column table from word rows, v6 first tries to resolve columns:
  1. Find the data lines (at least two numbers, numbers at least half of the words).
  2. Cluster the right edges of their number tokens, with a tolerance of 3 points, into columns. The row-label column is everything left of the first number column.
  3. Assign every word below the header to a cell. The row label drops dot leaders and trailing periods.
  4. Assign the header words, the lines above the first data line, to columns by centre.

  The table becomes a normal grid: a header row and body rows, rendered as Markdown or plain text by the existing `table_row_groups`. Its attributes record `reconstruction: "word-columns"`.
- **A3. Bounds.** At most 30 columns and 2,000 words per table; above that the v5 path is used. No new dependency.
- Not in this spec: stitching GAO's split table into one table (its rows stay as paragraphs under the caption); superscript footnote marks in row labels ("20202" for 2020 with note 2, as in v5); tables in OCR'd scans (USGS f5-q3).

## Part B: row passages, `section-token-v4` and `parent-child-v4`

- **B1.** A table block whose attributes carry `table.rows` and `table.header_row`, and whose text has one line per row (Markdown: header, divider, rows; plain text: header, rows), yields one piece per body row:
  - Its text maps to the block's header line(s) when they fit the passage limit, the line(s) of the row's group label (if any) and the row's line. These are exact source spans, so the evidence inspector still highlights them.
  - Group-label rows give no passage of their own unless no row follows them.
  - A table whose lines do not match its rows (cut, cells omitted) is chunked as in v3.
- **B2.** Row pieces are never packed with other pieces and never merged as short chunks. A row longer than the hard limit is split as in v3.
- **B3. Searched text:** `Section: <path>\n\n<label>: <first cell>. <column>: <value>; …`, with empty cells left out. The group label, if any, comes first. The searched text is embedded; the passage text is what the answer model and the evidence inspector see. Provenance records `table_passage: "row-v1"`.
- **B4.** `parent-child-v4` parents are built exactly as in v3; within a parent, each table row is its own child.

## Part C: editor and docs

- The Extract node offers `layout-ocr-v6` and the Chunk node offers the v4 versions, with the existing upgrade notices for saved v5/v3 nodes. New drafts switch only under D6.
- The capabilities endpoint, docs site and `docs/architecture.md` describe the new versions.

## Slices

| Slice | Content | Acceptance |
| --- | --- | --- |
| 0 | Measure first: prototype A1, A2 and B on GAO (G3) and Census (F2); embed the new passages (under $0.05); rank every question on those two files by vector search and by the Slice 0 BM25 | Results in `docs/qa/table-rows-2026-10/`. If the prototype does not bring g3-q2 into the top 5, or brings neither f2-q9 nor f2-q10 into it, or loses a question on these files that A5 found, stop and report before building |
| 1 | A1 in `layout-ocr-v6` | Unit tests on the GAO geometry; v5 output byte-identical on the fixture PDFs |
| 2 | A2 in `layout-ocr-v6` | Unit tests for column resolution, header assignment, group labels, the fallback and the bounds; Census Table A-2 page 22 gives the expected header and the 2015 row |
| 3 | B in `section-token-v4` and `parent-child-v4` | Chunking tests for row passages, spans, labels, fallback and splitting; v3 output byte-identical |
| 4 | Part C | Vitest, lint, typecheck, build; browser check |
| 5 | Proof round, paid (D6, D7) | Rounds A6 (v6 + section-token-v4) and A6p (v6 + parent-child-v4) against A5/A5p on the same questions, scored blind with the spec 0004 rubric; switch new drafts only under D6 |

## Verification

- Backend unit tests for every slice; PostgreSQL tests where run handling or persistence is touched; the full backend suite in the isolated stack.
- Frontend lint, typecheck and tests with `--maxWorkers=1` (low memory); the editor checked in the browser at `http://127.0.0.1:5273`.
- The real-source harness and blind scoring for the proof round, with 10 labels for the owner to spot-check.
- Each slice is committed on local `main`; nothing is pushed until the owner asks.
