# Search v3 measurements (spec 0010)

Spec: `docs/specs/0010-search-finds-table-rows-and-short-facts.md`. Questions, files and the A3 indexes are those of spec 0009's round A3 (`docs/qa/extract-v5-2026-10/README.md`).

## Slice 0: measure before building (2026-10-10, $0.013 in embeddings)

Scripts and per-question results are in `raw/`: `hybrid_sim.py` (vector top 50 from the app's own search, keyword top 50 in SQL, fused with the app's reciprocal-rank rule), `exp_indexes.py` (experiment indexes), `merge_probe.py` (the merged-chunk test), `sim_*.json`. A question counts as found when one supplied text in the top 5 holds all its reference phrases, as in the harness.

### Keyword search (Part A)

On the A3 indexes, 49 answerable file questions:

| Search | Hit@1 | Hit@5 |
| --- | --- | --- |
| Vector (today) | 26 | 40 |
| Existing `keyword` / `hybrid` modes | 0 / 26 | 0 / 40 (hybrid equals vector: the keyword half returns nothing for any question) |
| Keyword, content words OR-ed, over section path + text | 15 | 32 |
| Hybrid with that keyword half | 29 | 39 (gains g8-q1; loses f4-q3, g5-q2) |
| Keyword with only rare words (in at most 5% of chunks) | 15 | 33 |
| Hybrid with the rare-word keyword half | 26 | 39 (gains g8-q1; loses f1-q4, g5-q2) |

On smaller chunks (below) the OR-ed keyword half is worse still: PostgreSQL's `ts_rank_cd` has no notion of how rare a word is, so words such as "income", "median" and "2022", present in nearly every Census chunk, drown out "2015" and "A-2". Rare-word selection only brings hybrid back level with vector. **No keyword variant meets D2 (no question lost), and none finds the three target questions.**

### Chunking (Part B)

Experiment indexes of the Census report and the Eurostat report, extractor v5, otherwise the A3 settings; 12 answerable questions on these two files. A3 vector search finds 8 in the top 5 and 6 at rank 1.

| Chunks | Chunks built | Vector top 5 / rank 1 | Hybrid (OR) | Hybrid (rare words) |
| --- | --- | --- | --- | --- |
| A3: section chunks, 600 target | 455 + 894 | 8 / 6 | 7 / 6 | 8 / 6 |
| E1: section chunks, 200 target | 2,961 | 9 / 4 | 3 / 1 | 9 / 7 |
| E2: `parent-child-v1` defaults (240-token children, 900-token parents) | 2,665 | **9 / 7** | 6 / 4 | 9 / 7 |
| E3: `parent-child-v1`, 120-token children | 3,460 | 9 / 7 | 7 / 4 | 9 / 6 |

- **Parent-child (E2) is the best and already exists.** Against A3 it loses no question and finds the Census 1990 row (f2-q10) at rank 1; no other setting found it in the top 5 except small section chunks (rank 4), which push four other Census questions down.
- **The Census 2015 row (f2-q9) is still not found.** In E2 the child with the 2015 row ranks 35th; its parent is supplied at rank 10 through a neighbouring child. Table A-2's children are runs of year rows that an embedding barely tells apart ("2015" against "2012"). Only E1 with rare-word hybrid reached it (rank 5), at the cost of the 1990 row.

### Short heading chunks (B2)

The Eurostat callout "381 décès pour 100 000 habitants" sits in a run of three tiny chunks on p. 21 (36, 12 and 68 tokens; big chart labels are read as headings, each starting a section). 529 of the A3 Eurostat index's 1,025 chunks are under 40 tokens.

Test: the run of chunks under 40 tokens around the callout was appended to the chunk before it on the same page (201 tokens with its section prefix), indexed as one TXT chunk through the app, and searched with f4-q1. Its distance is 0.197; today's best chunk for that question is at 0.234. **The merged chunk would rank first.**

### What this changes in the plan

1. **Drop Part A from this spec.** Fixing the keyword half as specified loses questions (D2 fails) and finds none of the targets; a rarity-weighted version only ties vector. The finding stands on its own: the existing `keyword` and `hybrid` modes return no keyword matches for natural questions, so `hybrid` has always equalled `vector`. That deserves its own fix, with proper rarity weighting (BM25-style), as a separate spec.
2. **Part B1 becomes "use parent-child", not a new table chunker.** Parent-child already keeps small searchable children and supplies the larger parent. Round A4 checks it on every file and question before it becomes the default for new drafts.
3. **Part B2 stays and is the main build:** merge runs of chunks under 40 tokens on the same page into the chunk before them, as a new chunking version for both section-token and parent-child.
4. **f2-q9 (Census 2015 row) is likely out of reach** of embedding search on this table. It is recorded as a known limit unless round A4 shows otherwise.

## Slice 1: short-chunk merge (2026-10-10, free)

`section-token-v2` and `parent-child-v2` (see the spec). Every test file was extracted with `layout-ocr-v5`, cleaned with the structure-aware profile and chunked with the default settings of both profiles, v1 and v2, without provider calls (`raw/v1_equiv.py`).

- **v1 is unchanged.** On all 15 files, v1 chunks and spans equal those of the code before this slice, for both profiles.
- **v2 removes most short chunks where they cluster.** Searchable chunks under 40 tokens, v1 to v2, section-token: Eurostat 525 to 17 (894 chunks to 394), NIST 57 to 23, BERT 26 to 2, GAO 23 to 4, Census 16 to 3, W-4 4 to 2, DfT 1 to 0. Parent-child children: Eurostat 532 to 29, NIST 86 to 56, BERT 31 to 7, GAO 25 to 5, Census 24 to 12. The scans, the spreadsheet, the PowerPoints (each short chunk starts a new slide), the DfE template and PLOS ONE are unchanged.
- **The Eurostat callout** "381 décès pour 100 000 habitants" is now in a 207-token chunk with the text before it on p. 21, in both profiles; Slice 0's 201-token merged chunk ranked first for f4-q1.

Whether retrieval improves without losing questions is measured in round A4 (Slice 3).

## Slice 3: round A4 (2026-10-10, about $0.12)

Rounds A4s and A4p repeat round A3 (extractor v5, the same 15 files, 49 answerable file questions and 44 asked questions, vector search top 5, `google/gemini-2.5-flash`) with only the chunking changed: A4s uses `section-token-v2`, A4p `parent-child-v2`, each with the settings a new pipeline gets. All six indexes published. Answers were scored by hand against the reference answers with the spec 0004 rubric (`docs/qa/real-source-2026-10/raw/manual_scores.csv`); the "Search v3" sheet of `docs/qa/real-source-2026-10/real-source-test.xlsx` has every number below. Spend by the harness's upper-bound estimate: $0.116 (index embeddings, query embeddings and 88 answers); the app-reported embedding charge was under $0.005, because unchanged chunks reused their embeddings.

| | A3 (v1) | A4s (section-token-v2) | A4p (parent-child-v2) |
| --- | --- | --- | --- |
| Hit@1 / Hit@5, 49 file questions | 26 / 40 | 27 / 41 | 30 / 42 |
| Answers correct or correctly declined, 44 asked | 37 | **38** | 35 |
| Answers right in A3 and wrong now | | none | f1-q1, g1-q2, g8-q2 |
| Answers wrong in A3 and right now | | f4-q1 | f5-q2 |

- **The Eurostat callout (f4-q1) is fixed by `section-token-v2`:** rank 1 and answered "381 décès pour 100 000 habitants". f4-q4 (greenhouse-gas fall) also moved into the top 5 (rank 3).
- **`section-token-v2` loses nothing.** The harness's one apparent retrieval loss, f1-q3, is its phrase rule: the abstract's wording "GLUE score to 80.5%" moved from rank 5 to 7, while the chunk stating "BERTLARGE obtains a score of 80.5" stays at rank 2 in A3 and A4s (rank 1 in A4p). Every answer right in A3 is right in A4s.
- **`parent-child-v2` does not meet the rule for becoming the default** (no question lost). It finds the Census 1990 row (f2-q10) and the USGS Illinois row (f5-q2), but loses three answers: g1-q2, because the 208-token child holding "$24,150 if you're head of household" no longer carries the worksheet text that matched the question (rank 1 → 6, distance 0.367 → 0.453); f1-q1 and g8-q2, where the supplied parents did not include the needed text. It also declined two questions whose answers it was given (f2-q10, f4-q1). New pipelines therefore keep `section-token-v2`; parent-child stays a choice in the editor.
- **Known limits, unchanged by chunking:** the Census Table A-2 rows (f2-q9 not retrieved in any round; f2-q10 retrieved only by parent-child and then declined), the USGS Kansas row (f5-q3, supplied at rank 2 but declined in every round), the DfT word limit (f6-q1) and the GAO mandates row (g3-q2). These need either retrieval that matches exact numbers and labels (the separate keyword-search spec) or table-aware answering, not chunk size.
- Website questions reuse the A1 index and were unchanged.
