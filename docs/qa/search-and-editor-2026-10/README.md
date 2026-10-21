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

## Proof round (Slice 6, 2026-10-22)

**Setup.** Real-source harness rounds (`backend/scripts/real_source/run.py`), the same 15 files, four websites, `structure-clean-v2`, the sizes a new pipeline gets and `google/gemini-2.5-flash` at temperature 0 as in A5 and A6p:
- **A7s:** `layout-ocr-v6` with `section-token-v5` (websites rebuilt from the R1 snapshot), answered through a Rerank node (`google/gemini-2.5-flash-lite`, vector top 30, keep 5; answer graph schema 3). Baseline A5, the current defaults.
- **A7:** `layout-ocr-v6` with `parent-child-v5`, websites reusing the A1 index as A6p does, with the same Rerank node. Baseline A6p, the best round so far.
- **A7s-plain and A7-plain:** the same A7s and A7 indexes answered without the Rerank node (vector top 5), added so that the chunkers' effect shows apart from the reranker's.

Indexes published (passages):

| Track | A5 | A7s | A6p | A7 |
| --- | ---: | ---: | ---: | ---: |
| Websites | 2,334 | 3,081 | A1 | A1 |
| Files (F1-F3) | 660 | 2,483 | 1,940 | 2,435 |
| Second file set | 506 | 678 | 981 | 1,037 |
| Spec 0009 files | 751 | 1,152 | 1,927 | 2,244 |

**Scoring.** Blind, by hand, with the spec 0004 rubric (`backend/scripts/clean_chunk/blind_rounds.py`): pairs A5:A7s:fgw and A6p:A7:fg with seed `search-editor-0015` ([`proof/`](proof/)), and A5:A7s-plain:fgw and A6p:A7-plain:fg with seed `search-editor-0015-no-rerank` ([`proof/no-rerank/`](proof/no-rerank/)). Every label and its reason was written before the key was read. The 100 A5 and A6p answers appear in both reviews and received the same label both times. [`proof/spot_check.md`](proof/spot_check.md) holds 10 random labels for the owner to check.

### Retrieval (all reference phrases in one supplied passage among the top 5; 77 answerable questions)

| Round | Top 5 | Rank 1 | Lost against A5 | Lost against A5 or A6p | Gained against the baseline |
| --- | ---: | ---: | --- | --- | --- |
| A5 (baseline) | 68 | 42 | | | |
| A6p (baseline) | 71 | 49 | | | |
| A7s-plain (no reranking) | 70 | 44 | none | f5-q2 | f2-q10, g3-q2 (vs A5) |
| A7-plain (no reranking) | 71 | 49 | none | none | none (vs A6p) |
| **A7s** | **75** | **65** | none | f5-q2 | f1-q3, f2-q9, f2-q10, g3-q2, g8-q1, g8-q2, w4-q7 (vs A5) |
| **A7** | **75** | **66** | none | none | f1-q3, f2-q9, g8-q1, w4-q7 (vs A6p) |

Still missed: A7 f6-q1 and g8-q2, A7s f5-q2 and f6-q1, none of them among the 30 candidates. Rank 1 rises by 23 (A5 to A7s) and 17 (A6p to A7).

### Answers (correct or correct-abstain)

| Pair | Questions | Before | After | Wins | Losses |
| --- | ---: | ---: | ---: | --- | --- |
| A5 → A7s | 56 | 51 | 51 | g3-q2 | f6-q1 |
| A6p → A7 | 44 | 39 | **42** | f2-q9, f2-q10, f6-q1, g8-q2 | f5-q2 |
| A5 → A7s-plain | 56 | 51 | **53** | f2-q10, g3-q2 | **none** |
| A6p → A7-plain | 44 | 39 | 39 | f2-q10 | f5-q2 |

From the same labels: A5 → A7 on the files is 39 → 42 with no loss (wins f2-q9, f2-q10, g3-q2); A7s-plain → A7s (adding the reranker to `section-token-v5`) loses f2-q10 and f6-q1; A7-plain → A7 (adding it to `parent-child-v5`) gains f2-q9, f6-q1 and g8-q2 and loses nothing.

**Repeats.** Each disputed answer was asked three more times on the same saved pipeline (`backend/scripts/real_source/repeat_check.py`, [`proof/repeat_check.json`](proof/repeat_check.json), $0.014). Correct answers out of four (the round's answer and three repeats):

| Question | Without reranking | With reranking |
| --- | --- | --- |
| f5-q2 (1,070 mgd) | A6p 1/4, A7-plain 0/4 | A7 3/4 |
| f6-q1 (250 words) | A5 4/4, A7s-plain 4/4 | A7s 1/4 |
| f2-q10 ($76,820) | A7s-plain 4/4 | A7s 0/4 |

- **f5-q2 is not a loss of the change.** A6p and A7-plain gave the model byte-identical passages in the same order (an OCR row of Table 1 with no column names, "Illinois 120 20 140 1,070 …"); the model picks 140 most of the time either way. Reranking moves that row to rank 1 and the answer is then mostly right.
- **f6-q1 and f2-q10 are real reranker losses on `section-token-v5`.** In f6-q1 the reranked prompt holds the same five passages as the plain one, in another order; the "Word limit 250 words" line sits between sections A3.2 and A3.3, and after reordering the model reads it as A3.3's and declines. In f2-q10 the reranker keeps a second Table A-2 row passage (retriever rank 15) and drops the table's title passage (rank 5), the only one that says "Income in 2022 dollars"; the model finds $76,820 but declines because nothing says it is in 2022 dollars.

### Cost and speed (answer runs)

| Pair | Median latency | Mean cost per question | Rerank call: mean / max cost, median time |
| --- | --- | --- | --- |
| A5 → A7s | 2.31 → 3.89 s (+1.58 s) | $0.00073 → $0.00125 | $0.00053 / $0.00128, 1.19 s |
| A6p → A7 | 2.44 → 3.86 s (+1.42 s) | $0.00107 → $0.00149 | $0.00045 / $0.00160, 1.16 s |

The added time includes retrieving 30 candidates instead of 5. **Fallbacks:** the reranker fell back to the retriever order in 12 of 180 retrieval checks and 7 of 100 answer runs (Slice 0: none in 462 calls). Each said "Reranking failed; retriever order used" and no answer failed. Most had no provider cost, so the call itself failed; the node does not record why. That is a follow-up (record the failure class).

### Against the spec's targets

| Target | A7s (`section-token-v5` + Rerank) | A7 (`parent-child-v5` + Rerank) |
| --- | --- | --- |
| At least 74 of 77 in the top 5 | 75, met | 75, met |
| Rank 1 up by at least 10 | +23, met | +17, met |
| No question lost that A5 or A6p found | f5-q2 lost (found by A6p), not met | met |
| At least 3 more correct answers than A5, none lost | 51 → 51, f6-q1 lost, not met | files 39 → 42, none lost, met (websites not asked, as in A6p) |
| At most $0.002 added per question | met | met |
| At most 1.5 s added median latency | +1.58 s, not met | +1.42 s, met |

`layout-ocr-v6` with `parent-child-v5` and the Rerank node meets every target on the files.

### Decision (D5)

- **New ingestion pipelines switch to `layout-ocr-v6` with `section-token-v5`** (and `parent-child-v5` when the parent-child method is chosen). Against the current defaults (A5) they lose no answer (51 → 53) and no top-5 hit (68 → 70). `parent-child-v5` loses no top-5 hit against A6p; its only answer difference is f5-q2, which the A6p baseline itself gets wrong 3 times in 4 on identical evidence. Saved pipelines keep their versions; older versions show **Upgrade extraction** and **Upgrade chunking**.
- **New answer pipelines stay without a Rerank node.** On `section-token-v5`, the chunker new pipelines use, it loses f6-q1 and f2-q10 (repeatable). It stays an optional node: with `parent-child-v5` it gains three answers, loses none and meets every target.
- **The default chunking method stays section-aware.** Parent-child with the reranker is the best measured setting for files, but parent-child-v5 was not measured on websites (A7 reuses the A1 website index), so changing the default method is left to the owner.

### Spend

By the harness's upper-bound estimate (provider-reported where the harness has it):

| Item | Cost |
| --- | ---: |
| Index embeddings, A7 and A7s | $0.132 estimate ($0.009 provider-reported) |
| Query embeddings | $0.0003 |
| Rerank calls in the retrieval checks | $0.088 |
| Answers: A7, A7s, A7-plain, A7s-plain (200) | $0.222 |
| Repeats (24 answers) | $0.014 |
| **Slice 6** | **$0.455** ($0.33 provider-reported) |

With Slice 0 ($0.370) this spec spent **$0.83 of its $1 cap**. The harness's cumulative total over all real-source rounds is $1.25 of its $2.50 cap.
