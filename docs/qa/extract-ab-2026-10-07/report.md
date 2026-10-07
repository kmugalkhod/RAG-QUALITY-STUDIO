# Extract v1 vs v2 results (spec 0004)

**Outcome under the pre-registered rule: inconclusive.**

| Net (wins − losses) | Value |
|---|---|
| affected_evidence | +1 |
| affected_correct | +4 |
| control_correct | +0 |
| control_evidence | +0 |
| unanswerable_correct | +0 |

| Category | Questions | v1 evidence hit@5 | v2 evidence hit@5 | v1 hit@5 with section | v2 hit@5 with section | v1 MRR | v2 MRR | v1 correct | v2 correct | v1 supported | v2 supported | correct W/L/T |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | 6 | 5/6 | 5/6 | 5/6 | 5/6 | 0.83 | 0.83 | 4/6 | 6/6 | 3/6 | 5/6 | 2/0/4 |
| C2 | 6 | 1/6 | 3/6 | 1/6 | 3/6 | 0.17 | 0.50 | 4/6 | 6/6 | 1/6 | 3/6 | 2/0/4 |
| C3 | 6 | 3/6 | 0/6 | 3/6 | 6/6 | 0.50 | 0.00 | 6/6 | 6/6 | 3/6 | 0/6 | 0/0/6 |
| C4 | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 | 1.00 | 4/4 | 4/4 | 4/4 | 4/4 | 0/0/4 |
| C5 | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 1.00 | 1.00 | 2/2 | 2/2 | 2/2 | 2/2 | 0/0/2 |
| C6 | 4 | 2/4 | 4/4 | 2/4 | 4/4 | 0.50 | 0.75 | 4/4 | 4/4 | 2/4 | 4/4 | 0/0/4 |
| K | 6 | 6/6 | 6/6 | 6/6 | 6/6 | 0.92 | 0.92 | 6/6 | 6/6 | 6/6 | 6/6 | 0/0/6 |
| U | 6 | n/a | n/a | n/a | n/a | n/a | n/a | 6/6 | 6/6 | 0/6 | 0/6 | 0/0/6 |
| all | 40 | 23/34 | 24/34 | 23/34 | 30/34 | 0.66 | 0.66 | 36/40 | 40/40 | 21/40 | 24/40 | 4/0/36 |

| Arm | Mean latency (ms) | Tokens | Generation cost (USD) | Failed runs |
|---|---|---|---|---|
| v1 | 2233 (40 runs) | 81741 (40/40 known) | 0.0268 (40/40 known) | 0 |
| v2 | 2213 (40 runs) | 73898 (40/40 known) | 0.0245 (40/40 known) | 0 |

Evidence hit@5 counts only chunk text, which is all the answer model receives; the "with section" columns also count the section path, which is embedded for search but not sent to the model. Correct means `correct` or `correct-abstain`. Correctness labels were given blind; `supported` was judged afterwards with the evidence visible, so it is not blind. Failed runs count as wrong. Unknown costs are not counted as zero.
