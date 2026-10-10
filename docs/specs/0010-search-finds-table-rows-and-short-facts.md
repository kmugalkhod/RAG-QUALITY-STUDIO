# 0010. Search that finds table rows and short facts

**Date**: 2026-10-10
**Status**: Approved 2026-10-10 (D1-D3). Slice 0 done; the revised plan below was approved by the owner on 2026-10-10 and replaces Parts A-C and the slices where they differ. Revised slices 1-2 done; round A4 (slice 3) next.

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

## Slice 0 result and approved revision (2026-10-10)

Measured 2026-10-10 for $0.013 (`docs/qa/search-v3-2026-10/README.md`):

- **Part A does not earn its place.** With content words OR-ed, hybrid search loses two questions vector finds and gains one; with only rare words it ties vector. No variant finds the target questions, so D2's "no question lost" condition cannot be met. PostgreSQL's ranking has no word-rarity weighting, which a proper fix would need.
- **Parent-child chunking, which already exists, beats the proposed table chunker.** On Census and Eurostat it loses nothing against today and finds the Census 1990 row (f2-q10) at rank 1.
- **Merging short same-page chunks finds the Eurostat callout.** The merged chunk would rank first for f4-q1 (distance 0.197 against 0.234 for today's best).
- **The Census 2015 row (f2-q9) stays out of reach:** the row chunks are near-identical runs of numbers to an embedding.

Revision, approved by the owner 2026-10-10:

1. Drop Part A from this spec. Record the keyword finding and propose a separate spec for a rarity-weighted (BM25-style) keyword search.
2. Replace B1 with "new drafts chunk with `parent-child-v1`", decided by round A4 on every file and question (no question lost).
3. Build B2 as the main change: a new chunking version for section-token and parent-child that appends runs of chunks under 40 tokens to the chunk before them on the same page.
4. Done-when becomes: f2-q10 and f4-q1 retrieved and answered, f2-q9 recorded as a known limit unless A4 finds it, no question lost, spend under $1.

D1 and D2 fall away with Part A; D3 (the $1 cap) stands.

### Revised slices

| Slice | Content | Risk |
| --- | --- | --- |
| 1 | `section-token-v2` and `parent-child-v2`: a section whose first chunk is under 40 tokens appends it to the chunk before it when both are on the same page (or both pageless) and the result fits the hard maximum; in parent-child the same rule applies to parents and, within each parent, to children. The merged chunk keeps the receiving chunk's section path. v1 output is unchanged. | Low |
| 2 | Editor and capabilities offer v2; new drafts use `section-token-v2`; saved v1 pipelines keep v1 and the editor offers the upgrade; docs | Low |
| 3 | Round A4 (paid, under $1): rebuild the files indexes with `section-token-v2` and `parent-child-v2`, ask every file question, "Search v3" sheet. If parent-child-v2 loses no question against A3, new drafts switch to it. | Low |

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
