# Keyword search with BM25: Slice 0 measurement (spec 0013, 2026-10-18)

Spec: `docs/specs/0013-keyword-search-bm25.md`. Scripts: `backend/scripts/keyword_search/slice0.py` (vector top 50 from the app's retrieval API; BM25 computed offline over each index's member passages with PostgreSQL's `to_tsvector('simple', section path + passage)`, k1 1.2, b 0.75, any question word may match; hybrid = the app's reciprocal-rank fusion, weight 0.5, constant 60) and `targets.py` (where BM25 ranks the passages that answer the target questions). Raw results: [`slice0.json`](slice0.json). Cost: query embeddings only, $0.0002.

A question counts as found when one supplied text (the parent for a child) in the top 5 holds all its reference phrases, the real-source harness's rule. Indexes are those of spec 0012's rounds A5 (`section-token-v3`, the default for new pipelines) and A5p (`parent-child-v3`).

## Results

| A5 (section-token-v3) | Vector | BM25 only | Hybrid |
| --- | ---: | ---: | ---: |
| 49 file questions: top 5 | 41 | 38 | **43** |
| 49 file questions: rank 1 | 23 | 25 | **30** |
| 28 website questions: top 5 | 27 | 24 | 26 |
| 28 website questions: rank 1 | 19 | 16 | **22** |

| A5p (parent-child-v3) | Vector | BM25 only | Hybrid |
| --- | ---: | ---: | ---: |
| 49 file questions: top 5 | 43 | 40 | 40 |
| 49 file questions: rank 1 | 29 | 26 | 29 |
| 28 website questions (A5 web index): top 5 / rank 1 | 27 / 19 | 24 / 16 | 26 / 22 |

- On A5, hybrid finds f1-q3, g8-q1 and g8-q2 (vector misses them; g8-q2 moves to rank 1) and puts seven more questions at rank 1, but **loses w1-q1** (Python tutorial deque, vector rank 2) **and g5-q2** (NISRA inactivity rate, vector rank 3): BM25 does not find either in its top 50, and fusion pushes them below rank 5.
- On A5p, hybrid gains nothing and loses f3-q4, g1-q2, g5-q2 and w1-q1.
- **None of the three targets is found** by BM25 or hybrid: f2-q9, f2-q10, g3-q2.

**The Slice 0 stop rule applies** (hybrid loses vector top-5 hits, and finds none of the targets), so spec 0013 is not built as written.

## Why the targets are not found (`targets.py`)

- **g3-q2 (GAO mandates of the Inhofe NDAA, 158):** the word "inhofe" is in no passage of the index. The extractor (`layout-ocr-v5`) kept only part of GAO's Table 2 "GAO Mandated Studies from Selected Recent Public Laws": its header, the row "P.L 117-328 | Consolidated Appropriations Act, 2023 | 97 | 191" (as a paragraph) and "Total | 358 | 706". The rows between them, the Inhofe NDAA's 158 mandates among them, were dropped. **This is an extraction bug**; no search can find text that was not extracted.
- **f2-q9 and f2-q10 (Census Table A-2, 2015 and 1990 rows):** the answering passage is one large table passage that starts with the header and holds many years of rows. "2015" appears in 31 of 660 passages and "1990" in 26, and the question's other words ("income", "median", "2022", "table") appear in hundreds, so BM25 ranks the passage 36th for f2-q9 and 6th for f2-q10. Embedding search has the same difficulty. **This is table granularity**: each passage holds many look-alike year rows. It is the spec 0008 open decision on giving appendix table rows their caption and header context.

## What this means

1. BM25 alone is not the fix for the remaining wrong answers. Its clear benefit is rank 1 (A5 files 23 → 30), but it loses questions that vector search finds, so it does not meet D4 for becoming the default.
2. The next useful work is in extraction and table chunking, not search:
   - an extractor fix for tables whose middle rows are dropped (GAO Table 2), as a new extractor version;
   - row-level table passages that repeat the table caption and column headers (Census Table A-2, USGS Table 1), as a new chunking version.
3. Hybrid with BM25 could still be offered as an opt-in search choice for its rank-1 gains, but not as the default; that needs an owner decision.
