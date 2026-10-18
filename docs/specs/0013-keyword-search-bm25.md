# 0013. Keyword search that ranks rare words: BM25 for the keyword and hybrid modes

**Date**: 2026-10-18
**Status**: Draft for owner approval. Nothing is built. D1-D6 below need a decision; each has a recommendation.

## Summary

Spec 0010 Slice 0 found that the `keyword` and `hybrid` search modes do not work for natural questions:

- The keyword half uses `websearch_to_tsquery`, which requires **every** word of the question to appear in a passage. For all 49 answerable file questions it returned nothing, so `hybrid` has always returned exactly what `vector` returns.
- OR-ing the words instead found more, but PostgreSQL's `ts_rank_cd` does not know how rare a word is. In the Census report, "income", "median" and "2022" appear in nearly every passage and drown out "2015" and "A-2". No variant tried in spec 0010 matched vector search, and none found the target table rows.

Embedding search is weak exactly where the remaining wrong answers are: rows of numbers and labels that look alike to an embedding ("2015" against "2012"). After spec 0012's round A5, these answerable questions still miss the top 5:

| Question | Needs | A5 vector rank | A5 answer |
| --- | --- | --- | --- |
| f2-q9 | Census Table A-2, 2015 row, "68,410" | not in top 5 | declined |
| f2-q10 | Census Table A-2, 1990 row, "76,820" | not in top 5 (parent-child: rank 1) | declined |
| g3-q2 | GAO, "Inhofe", "158" mandates | not in top 5 | declined |
| f5-q3 | USGS Table 1, Kansas row, "75" | rank 2 | declined |

This spec ranks keyword matches with BM25, the standard rarity-weighted formula, so that a rare label or number in the question ("A-2", "2015", "Inhofe") outweighs words found everywhere. Hybrid search then fuses a keyword ranking that actually returns results with vector search, as it was meant to. New answer pipelines switch to hybrid only if a real-source round loses no correct answer.

## Decisions for the owner

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | How to rank keyword matches | **BM25 computed by the app inside PostgreSQL** (k1 = 1.2, b = 0.75) from term statistics stored per index version. No new database extension: ParadeDB's `pg_search` would need a different PostgreSQL image and its own upgrade path. |
| D2 | Which words count | The existing `simple` analysis: lowercase, no stemming, so French and other languages work the same as English; numbers and codes such as "a-2" and "68,410" stay searchable. Any question word may match (OR), with BM25 weighting rare words up. Words are matched over the section path and the passage text, the same text that is embedded (spec 0010 found the section path helps). |
| D3 | Saved answer pipelines | Keep their search exactly as saved (`retrieval-v2`: every word required, `ts_rank_cd`). A new setting `keyword_ranking: "bm25-v1"` selects the new ranking; a missing value means the old one. Saved keyword or hybrid pipelines show **Saved with keyword matching that needs every word** and an **Upgrade search** button, like the chunking notice. |
| D4 | Default for new answer pipelines | **Hybrid with BM25** only if the proof round (Slice 4) loses no correct answer against round A5 (39 of 44 file questions, 12 of 12 website questions) and keeps every A5 top-5 hit. Otherwise new pipelines stay on vector search and hybrid remains a choice. |
| D5 | Index versions published before this spec | Their term statistics are built by a one-off backfill worker job after the migration, newest ready versions first. Until an index has them, a BM25 search of it falls back to vector-only results and says so in the run's search details ("Keyword statistics are still being built for this index"), never silently. |
| D6 | Spending | The proof round is the only paid work: query embeddings and about 100 answers, roughly $0.10, with a $1 cap. |

## Part A: term statistics (D1, D5)

- New table `index_terms`: for each index version, each passage member and each distinct term, the term frequency. New table `index_term_stats`: for each index version and term, the number of passages holding it; `index_versions` gains the passage count and mean passage length in terms. Index versions are immutable, so statistics are computed once.
- Built while a version is published, inside the same transaction that makes it ready, so a ready version always has statistics. A run that finds no change (spec 0012 D8) keeps the current version and its statistics.
- Terms come from `to_tsvector('simple', coalesce(embedding_text, text))` (section path and passage). The existing GIN index covers `text` only, so a new GIN index over the same expression finds candidates; a term found by that index is a term in the statistics.
- Bounded: at most 50,000 passages per index already; terms longer than 100 characters are skipped; the build is measured on the largest real-source index (the 2,334-passage website index of round A5) and on the 50,000-passage throughput fixture.
- Deletion: the statistics belong to their index version and are never shared across projects or versions.

## Part B: BM25 ranking (D2, D3)

- `KeywordSearch` and `HybridSearch` gain `keyword_ranking: Literal["ts-rank-v1", "bm25-v1"]`, default `"ts-rank-v1"` when absent. The retrieval snapshot records the algorithm (`retrieval-v3` for BM25), so every answer run shows how it searched.
- Query: the question's terms through the same analysis; candidates are passages of the index holding any term (GIN, OR query); score = Σ idf(t) · tf · (k1 + 1) / (tf + k1 · (1 − b + b · len / avg_len)), with idf(t) = ln(1 + (N − df + 0.5) / (df + 0.5)) from the index version's own statistics. Ties break on passage identity, as today.
- Terms in more than half of the passages are kept (BM25 already weights them near zero); a question with no indexed term returns no keyword results, and hybrid then equals vector, stated in the search details.
- Hybrid keeps reciprocal-rank fusion with the saved `vector_weight` and candidate counts.
- The evidence inspector labels the keyword score as "word-match score (BM25), higher is a closer word match; not a probability", beside the existing distance wording.

## Part C: answer editor (D3, D4)

- The Retriever settings show **Search by**: **Meaning** (vector), **Words** (keyword) or **Meaning and words** (hybrid), with Top k; fusion weight and candidate counts move under Advanced with **Reset to recommended**, in the spec 0005/0012 panel pattern.
- Saved `ts-rank-v1` keyword or hybrid nodes show the upgrade notice of D3; vector nodes are unaffected.
- Playground search shows which mode and ranking ran.

## Slices

| Slice | Content | Acceptance |
| --- | --- | --- |
| 0 | Measure first, under $0.01 (query embeddings only): BM25 computed offline in SQL over the A5 and A5p indexes; keyword-only, hybrid and vector top 5 for the 77 answerable questions | Per-question table in `docs/qa/keyword-search-2026-10/`. If hybrid-BM25 loses a vector top-5 hit, or finds none of f2-q9, f2-q10 and g3-q2, stop and report before building |
| 1 | Term statistics (Part A), migration, build at publish, backfill job, D5 fallback | Statistics equal a direct recount on test indexes; project and version scope tested; publish time on the largest index recorded |
| 2 | BM25 ranking (Part B) | Hand-computed BM25 scores on a small fixture; saved `ts-rank-v1` results byte-identical before and after; French and number/code queries tested |
| 3 | Answer editor and evidence wording (Part C) | Vitest, lint, typecheck, build; browser check on desktop and phone |
| 4 | Proof round, paid (D4, D6) | Rounds A6 (hybrid-BM25) against A5 on the same indexes and questions, scored blind with the spec 0004 rubric; switch new pipelines to hybrid only if no correct answer and no top-5 hit is lost |

## Verification

- PostgreSQL/pgvector integration tests for the statistics, ranking and fallback, in the isolated test stack.
- The real-source harness for the proof round, with the blind scoring script from spec 0012 and the owner spot-checking 10 labels.
- Retrieval latency for vector, keyword and hybrid measured on the largest index before and after.

## Out of scope

- ParadeDB or other search extensions, external search services.
- Rerankers, query rewriting, synonyms, stemming per language, agentic search (a later spec once this is measured).
- Table-aware answering: f5-q3's Kansas row is already retrieved and declined by the answer model; this spec does not change answering.
