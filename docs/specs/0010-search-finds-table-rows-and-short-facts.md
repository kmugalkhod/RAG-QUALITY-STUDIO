# 0010. Search that finds table rows and short facts

**Date**: 2026-10-10
**Status**: Approved 2026-10-10. The owner accepted the recommendation for D1-D3.

## Summary

Spec 0009 made the extractor deliver what three hard questions need, but search still does not find it (round A3, `docs/qa/extract-v5-2026-10/README.md`):

- **Census Table A-2** (f2-q9, f2-q10): the rows for 2015 and 1990 are in the index under their caption and header, but each row chunk is about 780 tokens of nearly pure numbers. Vector search ranks Table A-1, Figure 2 and the summary page above it.
- **Eurostat chart callout** (f4-q1): "381 décès pour 100 000 habitants" is in the index, but as its own 36-token chunk (the callout is read as a heading with no body), which ranks below the chart's title and axis chunks.
- Similar misses: a USGS typescript table row (f5-q2), the GAO mandates table (g3-q2), a DfT word limit split from its heading (f6-q1).

This spec fixes the search side: the keyword half of hybrid search, and how table rows and short headings are chunked. Extraction is not changed.

## What was measured before writing this (2026-10-10)

On the round A3 indexes, 49 answerable file questions, top 5:

| Search | Hit@1 | Hit@5 | Note |
| --- | --- | --- | --- |
| Vector (what every pipeline uses today) | 26 | 40 | |
| Keyword (existing `keyword` mode) | 0 | 0 | **Returned no results for any question** |
| Hybrid (existing `hybrid` mode) | 26 | 40 | Identical to vector, because the keyword half returns nothing |
| Keyword with the question's content words joined by OR (probe, free) | | 35 | Finds g8-q1 (rank 1) and g8-q2 (rank 3), which vector misses |
| Same, over section path + text (probe, free) | | 35 | Eurostat callout rank 17 → 9; Census 2015 row not in top 50 → rank 36 |

Causes:

1. **The keyword half of hybrid search never matches a question.** `app/pipelines/retrieval.py` turns the query into `websearch_to_tsquery('simple', question)`, which requires every word, including "what", "was" and "according", to be in one chunk. Hybrid search has therefore always equalled vector search for natural questions, in every saved pipeline that chose it.
2. **Keyword search sees only the chunk text**, not its section path, so "Table A-2" or a heading above the text cannot match (`ix_chunks_lexical` indexes `chunks.text`).
3. **Table rows are chunked like prose.** Header-repeating row groups are packed into 600-800-token chunks; one year's row is a small part of a long run of numbers.
4. **A heading with no body becomes its own chunk.** Eurostat has 360 single-line chunks (median chunk 24 tokens); its callouts and chart titles are among them.

A keyword fix alone (probe rows 4-5) does not reach the Census rows; a chunking fix is needed too. Whether the two together reach them is the first thing this spec measures (Slice 0), before anything ships.

## Decisions for the owner

| ID | Decision | Recommendation (approved 2026-10-10) |
| --- | --- | --- |
| D1 | Saved answer pipelines and experiments that use `keyword` or `hybrid` | Keep their recorded behaviour. The fixed keyword matching is a new retrieval algorithm version (`retrieval-v3`); a saved configuration without the new setting runs `retrieval-v2` as recorded. New drafts get v3. |
| D2 | Default search for new answer pipelines | Switch from `vector` to `hybrid` (v3) only if round A4 shows Hit@5 at least as high as vector and no question that vector found is lost. Otherwise keep vector and offer hybrid. |
| D3 | Spending cap for the proof | $1, as before (A3 cost $0.033). |

## Part A: keyword search that matches questions (`retrieval-v3`)

- A1. The keyword half searches for any of the question's content words, not all of them: the question is reduced to its words minus a fixed English and French stop-word list, numbers kept whole (`2015`, `68,410`, `A-2`), joined with OR. Ranking stays `ts_rank_cd`; rank fusion stays reciprocal-rank with constant 60.
- A2. The keyword document is the chunk's section path plus its text (the stored `embedding_text`), so captions and headings can match. A migration adds the matching GIN index; the old index stays until no v2 configuration needs it.
- A3. The setting is explicit and versioned: `keyword_matching: "all_terms" | "any_terms"` on keyword and hybrid search. A saved configuration without it means `all_terms` over chunk text (v2, unchanged). New drafts and the editor's form use `any_terms`; the algorithm snapshot records `retrieval-v3` and the matching mode.
- A4. Bounds stay as today (candidate counts, top k, query length); the stop-word list is fixed in code and versioned with the algorithm.

Code: `app/pipelines/retrieval.py`, `app/schemas/retrieval.py`, `frontend/src/lib/retrieval.ts`, `frontend/src/components/RetrievalSettingsForm.tsx`, one Alembic migration.

## Part B: chunks that keep table rows and short facts findable (new chunking version)

- B1. **Table rows in small chunks.** In the section-aware chunker, a table's row groups are chunked on their own, at most about 200 tokens each (a new setting, `table_target_tokens`), and every chunk keeps the table's caption (section path) and repeated header. Prose chunking is unchanged.
- B2. **Short headings join their text.** A heading-only chunk under 40 tokens (a callout, a chart title) is merged into the next chunk on the same page instead of standing alone; if there is none, into the previous one. Its text stays in the merged chunk and the section path follows the merged chunk.
- B3. These ship as a new chunking configuration version (`section-token-v2`). Indexes built with `section-token-v1` are unchanged; changing chunking creates a new index version, as today.
- B4. Slice 0 compares B1 with the existing `parent-child-v1` profile (small child chunks matched, parent supplied to the model) on the Census tables. If parent-child already finds the rows, B1 becomes "use parent-child for table rows" rather than a new chunker.

Code: `app/ingestion_content/chunking.py`, `app/schemas/ingestion.py`, the chunk settings in the ingestion editor.

## Part C: proof

- C1. Round A4: rebuild the files, spec 0008 and spec 0009 indexes with the new chunking, and ask every file question (A2 and A3 sets) with vector, hybrid v2 and hybrid v3.
- C2. A "Search v3" workbook sheet: Hit@1/Hit@5 per mode, questions gained and lost, answer labels for the chosen default.

**Done when:** f2-q9, f2-q10 and f4-q1 are retrieved in the top 5 and answered correctly with the new defaults; no question that vector search found in A3 is lost; saved v2 configurations return exactly what they returned before; spend stays under $1.

## Slices

| Slice | Content | Risk |
| --- | --- | --- |
| 0 | Measure, before building: keyword OR + section path, B1 (table chunks of ~200 tokens) and parent-child on Census, B2 on Eurostat, using rebuilt test indexes (embedding cost only, a few cents) | Low |
| 1 | Part A, `retrieval-v3`, migration, editor setting; saved v2 behaviour proved unchanged | Medium |
| 2 | Part B, `section-token-v2` (or parent-child for tables, per Slice 0) | Medium |
| 3 | Defaults for new pipelines per D2, docs | Low |
| 4 | Round A4 and the "Search v3" sheet (Part C), paid, under $1 | Low |

## Verification

Unit tests for query reduction (stop words, numbers, French), matching modes and fusion; PostgreSQL tests for the lexical index, v2/v3 equivalence on saved settings and project scoping; chunking tests for table groups and heading merge; the full backend suite in the isolated stack; frontend lint, typecheck and tests with `--maxWorkers=1`; the retrieval form checked in the browser at `http://127.0.0.1:5273`. Each slice is committed on local `main`; nothing is pushed until the owner asks.

## Out of scope

- Extraction changes (spec 0009 is done).
- Rerankers or new providers, and changing the embedding model.
- OCR accuracy for low-quality scans; non-English OCR packs.
- Website chunking (the website track keeps its A1 index unless a slice shows it is affected).
