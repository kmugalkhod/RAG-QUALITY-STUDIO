# Table rows kept and findable: Slice 0 measurement (spec 0014, 2026-10-18)

**Spec:** `docs/specs/0014-table-rows-kept-and-findable.md`.

**Script:** `backend/scripts/table_rows/slice0.py`.
- It reprocesses the Census report (F2) and the GAO testimony (G3) with `layout-ocr-v6` and v4 chunking, through the worker's own extract, clean and chunk path, with each round's saved settings otherwise unchanged.
- The new passages replace those documents' passages in the round's A5 or A5p index; every other passage keeps its stored embedding.
- All 37 answerable questions of the two tracks (F1-F3 and G1-G8) are then ranked over the old and the new passage sets:
  - by cosine similarity (vector);
  - by the spec 0013 Slice 0 BM25 over each passage's searched text;
  - by their reciprocal-rank fusion (hybrid, weight 0.5, constant 60).

A question counts as found when one supplied text (the parent for a child) in the top 5 holds all its reference phrases, the real-source harness's rule.

**Raw results:** [`slice0.json`](slice0.json).

**Cost:** about $0.04 at most, for the new passages and the question embeddings. This is an upper bound on UTF-8 bytes at the list price.

## Results

| Top 5 of 37 questions | A5 old | A5 new | A5p old | A5p new |
| --- | ---: | ---: | ---: | ---: |
| Vector | 31 | **33** | 32 | **33** |
| BM25 | 28 | 31 | 29 | 32 |
| Hybrid | 33 | **36** | 29 | 31 |

| Target | A5 vector, old → new | A5 hybrid, old → new | A5p vector, old → new | A5p hybrid, old → new |
| --- | --- | --- | --- | --- |
| g3-q2 (GAO, Inhofe, 158) | — → **1** | — → **1** | — → **1** | — → **1** |
| f2-q10 (Census, 1990, 76,820) | — → **2** | — → **2** | 1 → 1 | 2 → **1** |
| f2-q9 (Census, 2015, 68,410) | — → — | — → **3** | — → — | — → **1** |

- **No vector top-5 hit is lost** in either round. Every other question changed only in rank, and only for the better or not at all:
  - on A5, f2-q5 went from rank 2 to 1 and f2-q6 from 2 to 1;
  - on A5p, f3-q5's hybrid rank went from 2 to 1.
- **Hybrid still loses g5-q2** (NISRA) on A5, as in spec 0013 Slice 0, and on A5p it also loses f3-q4 and g1-q2. That is a property of the BM25 fusion, not of this change; the questions are lost the same way with the old passages.
- **f2-q9 (2015) is still not in the vector top 5.** Its row passage is now labelled "ALL RACES. … 2015 … Median income (dollars) Estimate: 68,410", and keyword matching finds it, but among nearly a thousand look-alike rows the embedding does not rank it first.
- **Passage counts:**
  - F2 went from 511 to 1,277 passages on A5, 945 of them table rows, and from 1,605 to 1,586 on A5p (parents as in v3, rows as children).
  - G3 went from 73 to 79 passages.

**The Slice 0 stop rule does not apply:**
- g3-q2 is in the top 5;
- f2-q10 is in the top 5 (and f2-q9 is, with hybrid search);
- no question on these files that A5 found is lost.

The build continues with Slices 1-3.

## What changed in the extracted text

- **GAO Table 2 (pages 2 and 5):** the row "P.L 117-263 | James M. Inhofe National Defense Authorization Act for Fiscal Year 2023 | 158 | 312" is now kept.
  - v5 dropped it twice. On page 5 the row's block started 0.00001 points inside the ruled header's box; on page 2 the "158 | 312" block overlapped it by 0.7 points.
  - v6 drops only text lines that lie at least half inside a table.
- **Census Table A-2 (pages 22-36) and the other sideways appendix tables:** the columns are named. The header now reads "Race and Hispanic origin of householder and year | Number (thousands) | Total | Under $15,000 | … | Median income (dollars) Estimate | Median income (dollars) Margin of error1 (±) | Mean income (dollars) Estimate | …", and every row has one value per column. v5 had a run-together header and one text line per row.

## Known limits

- **Footnote marks after years stay in the row label**, as in v5: "20202" is 2020 with note 2.
- **"Percent distribution" spans eight columns but is attached only to the two it is printed over.**
- **A group label carried onto a continuation page appears in the searched text but not in the passage text the answer model sees.** For example, the ALL RACES rows before 1990 on page 23 lack the label in their passage text.
- **GAO Table 2's rows stay paragraphs** under the table's caption, not table rows.

## Proof round (Slice 5, 2026-10-18)

**Setup.** Rounds A6 and A6p of the real-source harness (`backend/scripts/real_source/run.py`) repeat rounds A5 and A5p, changing only the extractor and chunking versions:
- **The same everywhere:** the 15 files, `structure-clean-v2`, the sizes a new pipeline gets, vector search top 5, and `google/gemini-2.5-flash` at temperature 0.
- **A6:** `layout-ocr-v6` with `section-token-v4`. It also rebuilds the four websites from the R1 snapshot, because v4 also chunks website tables by row.
- **A6p:** `layout-ocr-v6` with `parent-child-v4`.

Every index published:

| Index | Before (A5 / A5p) | After (A6 / A6p) |
| --- | ---: | ---: |
| Websites, A6 | 2,334 | 3,017 |
| Files (F1-F3), A6 | 660 | 1,431 |
| Second file set, A6 | 506 | 667 |
| Spec 0009 files, A6 | 751 | 1,094 |
| Files (F1-F3), A6p | 1,955 | 1,940 |
| Second file set, A6p | 905 | 981 |
| Spec 0009 files, A6p | 1,857 | 1,927 |

**Scoring.** Answers were scored blind with the spec 0004 rubric, using `backend/scripts/clean_chunk/blind_rounds.py` with this spec's own seed (`BLIND_SEED=table-rows-0014`). Every label and its reason was written before the key was read. The review, labels, key and results are in [`proof/`](proof/), and [`proof/spot_check.md`](proof/spot_check.md) holds 10 random labels for the owner to check.

### Answers (correct or correct-abstain)

| Pair | Questions | Before | After | Wins | Losses |
| --- | ---: | ---: | ---: | --- | --- |
| A5 → A6 (files, section-token) | 44 | 39 | 38 | f2-q10, g3-q2 | **f6-q1, f6-q2, g5-q2** |
| A5 → A6 (websites) | 12 | 12 | 12 | | none |
| A5p → A6p (files, parent-child) | 44 | 38 | **39** | g3-q2 | none |

### Retrieval (phrase in the top 5)

| Pair | Questions | Top 5 before → after | Rank 1 before → after | Lost from top 5 | Gained |
| --- | ---: | --- | --- | --- | --- |
| A5 → A6, files | 58 | 41 → 41 | 23 → 27 | f6-q2, g5-q2 | f2-q10, g3-q2 |
| A5 → A6, websites | 32 | 27 → 27 | 19 → 16 | none | none |
| A5p → A6p, files | 58 | 43 → **44** | 29 → 31 | none | g3-q2 |

- **f2-q9** is still not retrieved in any round.
- **f2-q10** is rank 2 in A6 and stays rank 1 in A6p. The A6 answer is correct; the A6p answer declines, as A5p's did.
- **g3-q2** is now answered correctly in both rounds ("158 GAO mandates"). A5 declined it, and A5p answered "more than 20 actions".

### Why section-token-v4 loses

All three losses are in non-PDF table files, which `layout-ocr-v6` does not change. The cause is the v4 row passages:

- **f6-q1 and f6-q2 (DfT DOCX template).** The answers are spread over several rows of one table: a list of asset categories, and a word limit stated in the row next to its section's name. A one-row passage never holds the whole answer. Under `parent-child-v4` the parent still holds the table, and both are answered (f6-q2), or declined as before (f6-q1).
- **g5-q2 (NISRA XLSX).** The sheet's first row is its title, not its column names, so every row passage pairs its values with the title. The workbook's table-of-contents rows then rank above the answer row.

### Decision (D6)

**New pipelines stay on `layout-ocr-v5` with `section-token-v3`.** `section-token-v4` loses three correct answers and two top-5 hits, so the spec's condition is not met. `layout-ocr-v6`, `section-token-v4` and `parent-child-v4` remain available for saved pipelines and through the API.

`layout-ocr-v6` with `parent-child-v4` meets the condition on its own: it loses no answer and no top-5 hit, and it finds g3-q2 and f2-q10. But new drafts use the section-token profile, and making parent-child the default is outside this spec. That choice, and the other follow-ups, are recorded for the owner in `docs/implementation-plan.md`.

### Spend

By the harness's upper-bound estimate:

| Round | Index embeddings | Query embeddings | Answers | Total |
| --- | ---: | ---: | ---: | ---: |
| A6 | $0.065 | $0.0001 | $0.036 (56) | $0.100 |
| A6p | $0.037 | $0.0001 | $0.047 (44) | $0.085 |

That is **$0.185** for this round, plus $0.04 in Slice 0, against this spec's $1 cap. The harness's cumulative total over all real-source rounds is $0.79; the owner raised its cap to $2 on 2026-10-18.

### Browser check (Slice 4)

At `http://127.0.0.1:5273`, on desktop (1,280 px) and phone (390 px), with no page errors:
- the saved A6 pipeline (`layout-ocr-v6`, `section-token-v4`) shows no **Upgrade extraction** or **Upgrade chunking** notice;
- the saved A2 pipeline (`layout-ocr-v4`, `section-token-v1`) still shows both.

An unrelated existing fault was seen: opening an ingestion pipeline's URL without `?kind=ingestion` renders it in the answer editor, which fails on its node types and leaves a blank page.
