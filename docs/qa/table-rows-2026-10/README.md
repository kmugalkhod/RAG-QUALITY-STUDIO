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
