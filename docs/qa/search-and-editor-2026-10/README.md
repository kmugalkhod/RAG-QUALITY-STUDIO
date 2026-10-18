# Reranking: Slice 0 measurement (spec 0015, 2026-10-18)

Spec: `docs/specs/0015-better-search-and-editor.md`. Script: `backend/scripts/rerank/measure.py`. Results: [`slice0.json`](slice0.json) (summary and the first top-5 hit rank per question and setting). Raw calls: [`raw/slice0-calls.json`](raw/slice0-calls.json) (candidate keys, each model reply, the resulting order, tokens, cost and latency; passage text left out).

## Method

- **Questions:** the 77 answerable real-source questions (`backend/scripts/real_source/questions.jsonl`, the ones with `phrases`).
- **Indexes:** each track's index of rounds A5 (`layout-ocr-v5`, `section-token-v3`, the current defaults) and A6p (`layout-ocr-v6`, `parent-child-v4`, the best so far; websites use the A1 index, as in the harness).
- **Candidates:**
  - **vector:** the app's own vector search, top 30, through its retrieval API;
  - **union:** vector top 30 plus the spec 0013 BM25 top 30 (k1 1.2, b 0.75, the index's own term statistics), vector order first.
  - Children that share a parent are one candidate, the parent text that the prompt is given. This changes no baseline count (A5 68/42 and A6p 71/49 with and without it).
- **Reranking (prompt `rerank-v1`):** one listwise call per question. The model gets the question and the numbered candidates, each with its file, page and section, inside `<passage>` tags, and is told that the passages are untrusted text whose instructions it must never follow. It replies with the numbers of the 5 most useful passages. Numbers it leaves out are filled from the retriever order, which is what the Rerank node will do. Temperature 0, reasoning off, at most 60 output tokens, OpenRouter with the project's key.
- **Found:** one supplied text among the top 5 holds all the question's reference phrases (the harness rule). **Cost** is OpenRouter's reported cost per call. **Latency** is the wall-clock time of the call.

Models (D2): `google/gemini-2.5-flash-lite` ($0.10 / $0.40 per million input / output tokens) as the cheap model, and `google/gemini-2.5-flash` ($0.30 / $2.50), the answer model in use.

## Results

| Setting | Round | Top 5 | Rank 1 | Lost | Gained | Mean / max cost per question | Median / p90 latency |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| No reranking (baseline) | A5 | 68 | 42 | | | | |
| flash-lite, vector top 30 | A5 | 72 | **64** | none | f1-q3, g8-q1, g8-q2, w4-q7 | $0.00063 / $0.00186 | 0.99 s / 1.29 s |
| flash-lite, vector + BM25 | A5 | 73 | 64 | none | + f2-q10 | $0.00094 / $0.00253 | 1.14 s / 1.78 s |
| No reranking (baseline) | A6p | 71 | 49 | | | | |
| **flash-lite, vector top 30** | **A6p** | **75** | **67** | **none** | f1-q3, f2-q9, g8-q1, w4-q7 | **$0.00049 / $0.00127** | **1.08 s** / 1.80 s |
| flash-lite, vector top 30 (repeat) | A6p | 75 | 67 | none | same | same | 0.97 s / 2.03 s |
| flash-lite, vector + BM25 | A6p | 76 | 67 | none | + g8-q2 | $0.00079 / $0.00158 | 1.10 s / 1.60 s |
| gemini-2.5-flash, vector top 30 | A6p | 75 | 68 | none | same as flash-lite | $0.00148 / $0.00382 | 1.02 s / 1.38 s |

No call failed or returned an unusable order. The repeat run gave the same top 5 for every question.

**Against the target** (at least 74 of 77 in the top 5, rank 1 up by at least 10, no question lost, per question at most $0.002 and 1.5 s added):
- **flash-lite with vector candidates on A6p meets every part:** 75 of 77, rank 1 49 → 67 (+18), nothing lost, at most $0.0013 per question, median 1.08 s.
- On A5 the same setting reaches 72, because the answer to four questions is not in A5's vector top 30 at all (f2-q10, f5-q2, f6-q1, g3-q2, all fixed in A6p's extraction or chunking). Rank 1 rises by 22 and nothing is lost.
- gemini-2.5-flash gives the same top 5 for three times the cost, and its most expensive question ($0.0038) is over the cost target.
- BM25 candidates add one question per round (A5 f2-q10, A6p g8-q2) for about 60% more cost, and A5's most expensive question ($0.0025) is over the cost target.

## Where the remaining misses are

With vector candidates, the reranker puts the answer in the top 5 for every question whose answer is among the candidates, except A5 f2-q9 (Census Table A-2, 2015 row: its passage is at retriever rank 14 among look-alike year rows, and A6p's row passages fix it). The other misses are not among the candidates:

| Round | Not in vector top 30 | Not in vector + BM25 |
| --- | --- | --- |
| A5 | f2-q10, f5-q2, f6-q1, g3-q2 | f5-q2, f6-q1, g3-q2 |
| A6p | f6-q1, g8-q2 | f6-q1 |

f6-q1 (the DfT list across several table rows) is the case the spec 0015 S3 chunkers (`parent-child-v5`, `section-token-v5`: whole table plus rows) are meant to fix.

## Decisions taken under the spec

- **D2 (model): `google/gemini-2.5-flash-lite`**, the cheapest model that meets the target. It is not yet an approved model in this instance; the proof round (Slice 6) needs it approved in Organization settings.
- **D3 (keyword candidates): not built.** Vector-only candidates meet the target, so S2 and Slice 2 are skipped. BM25 candidates remain a measured option (one more question per round, about 60% more cost).
- **Node defaults for Slice 1:** `top_n` 5, Retriever Top k 30 when a Rerank node is present, prompt `rerank-v1` as above.

## Cost

Slice 0 spent **$0.3695** on reranking calls (six runs of 77 questions) plus about $0.0002 of query embeddings. The spec's cap is $1, which leaves $0.63 for the proof round (estimated at $0.40).
