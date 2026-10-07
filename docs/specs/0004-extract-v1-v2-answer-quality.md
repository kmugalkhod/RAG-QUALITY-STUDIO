# 0004. Extract v1 vs v2: does better extraction improve answers?

**Date**: 2026-10-07
**Status**: Run on 2026-10-07. Outcome under the rule: **inconclusive** (see Results). The owner's review of the questions and spot-check of the labels are still pending.

## Summary

Build two indexes from the same documents. They are identical except for the Extract node: one uses `layout-ocr-v1`, the other `layout-ocr-v2`. Ask the same reviewed questions through two answer pipeline versions that differ only in which index they search. Check whether the right evidence was retrieved, and score each answer blind, without knowing which version produced it. Use the result to decide whether to keep investing in the Extract engine or to stop and simplify the Extract panel.

## Context

The Extract v2 plan (`docs/extract-node-improvement-plan.md`) fixed column reading order, table truncation, missing headings, fragmented OCR paragraphs, and DOCX/CSV/XLSX tables without headers. The corpus baseline (`docs/ingestion-corpus-baseline.md`) proves the extraction output improved. It does not prove that retrieval or answers improved. The single paid run on 2026-10-07 only showed that v2 publishes and that retrieval ranked matching chunks first for a few questions.

The owner questioned whether this work, and the many technical settings it exposes, is needed at all. This spec answers that question with a measured comparison and a decision rule fixed in advance. It changes no product behavior.

What already exists (verified on 2026-10-07):

- **Answer pipeline runs.** `POST /api/projects/{pid}/pipelines/{pipeline_id}/versions/{version_id}/runs` with `{"question": "..."}` runs a saved answer pipeline version. `GET /api/projects/{pid}/query-runs/{run_id}` returns its status (`succeeded`, `insufficient_evidence` or `failed`), the answer and a snapshot with timings, token usage, cost and ranked retrieval results (`Evidence`: rank, filename, page, section path, text).
- An answer pipeline's retriever points at a specific `index_id`. Two answer versions that differ only in `index_id` give a clean A/B.
- `layout-ocr-v1` can still be saved through the API (the schema accepts it). The editor only creates v2, so the v1 arm must be built through the API.
- Headings reach chunk text only with the `section_token` chunker and `add_heading_context: true` (`backend/app/ingestion_content/chunking.py`, the "Section: …" prefix). New pipelines in the editor default to `section_token`. The older `character_window` chunker ignores structure, and using it would hide the v2 heading fix.
- The answer prompt tells the model to begin with `INSUFFICIENT_EVIDENCE` when the evidence does not answer the question. The run then has status `insufficient_evidence`.
- The OpenRouter key is stored in the organization credential vault, and the answer model catalog default is `google/gemini-2.5-flash`.

**Why not the Experiments feature.** Experiments require an evaluator model and at least one RAGAS metric. The owner decided on 2026-10-07 that `google/gemini-2.5-flash` is too weak to act as a judge. Scoring is therefore done manually and blind (see Measures), and the questions run through the answer pipeline run API instead. `EVALUATOR_MODEL` stays unset.

## Requirements

**User story**: As the product owner, I want to know whether Extract v2 measurably improves retrieved evidence and answers on documents with columns, tables, headings and scans, so that I can decide whether further Extract work and its settings are worth keeping.

**Functional requirements**:

1. A deterministic generator writes the evaluation corpus. Each run produces identical files and SHA-256 hashes.
2. A reviewed set of 40 questions, each with a reference answer, a category, expected evidence terms and expected answer terms.
3. A script that, through the public API only, creates a dedicated project, uploads the corpus, builds the v1 and v2 indexes, creates two answer pipeline versions and asks every question through both. The script is resumable: it records IDs in a state file and reuses them instead of repeating paid work.
4. A free check, run before any paid step, previews extraction and chunks for both versions and reports which expected evidence terms appear in each version's chunks.
5. A scoring script that computes the automatic evidence measures and writes a blind review sheet with arm labels hidden.
6. Manual scores, recorded per answer against a fixed rubric, are merged with the automatic measures into a report.
7. Paid steps run only with an explicit `--allow-paid` flag. The script stops if the recorded cost exceeds the cap.
8. Results, the corpus manifest, the raw answers and the decision are saved under `docs/qa/extract-ab-<date>/` and summarized in `docs/implementation-plan.md`.

**Non-functional requirements**:

- No new dependency. Reuse the PDF, scan and DOCX approaches in `backend/tests/extract_corpus.py`.
- No changes to application code, schemas or migrations. If a defect is found, record it and fix it in a separate slice.
- The corpus is fictional and authored by us (CC0). No customer or personal data.
- A dedicated project keeps this evaluation isolated from developer data and from the QA project `d02d5e14…`.

## Design

### Corpus

Each document targets one v2 fix. Facts are placed so that a v1 defect separates a fact from the context a question needs.

| ID | Document | Targets | What v1 gets wrong |
|---|---|---|---|
| C1 | `field-guide-two-column.pdf`: 3 pages, two text columns; a fact's subject and value sit in consecutive paragraphs of the same column | F1 reading order | Paragraphs from the two columns interleave, so a subject and its value are pulled apart |
| C2 | `service-rates.pdf`: a ruled table of 60 rows across 2 pages, header on page 1 only | F2 tables | Rows lose their header, so "47.25" has no column name |
| C3 | `staff-handbook.pdf`: parts for Employees, Contractors and Interns, each with the same subsections (notice period, equipment return, expense limit) | F3, F4, F10 headings | Under Auto, headings are lost, so the three notice periods cannot be told apart |
| C4 | `scanned-memo.pdf`: 2 image-only pages of multi-line paragraphs | F5 OCR paragraphs | A paragraph becomes several line fragments |
| C5 | `vendor-register.docx`: a table with a header row | F8 DOCX tables | Cells lose their column names |
| C6 | `equipment.csv` and `budget.xlsx` | F8 CSV/XLSX tables | One block per row, without the header |
| K1 | `travel-policy.pdf`: a single-column digital PDF | Control | Nothing; v1 and v2 should match |
| K2 | `faq.txt` | Control | Nothing; plain text bypasses PDF extraction |

Facts use distinctive fictional values (for example, "Harbor Point depot", "14 calendar days") so that matching is unambiguous.

### Questions (40)

| Category | Questions | Notes |
|---|---|---|
| C1 two-column | 6 | Subject and value in consecutive same-column paragraphs |
| C2 table | 6 | Half of the rows on page 2 |
| C3 headings | 6 | Two per part; the body text never names the part |
| C4 scanned | 4 | Each answer spans the lines of one paragraph |
| C5 + C6 tables | 6 | 2 DOCX, 2 CSV and 2 XLSX lookups |
| K1 + K2 control | 6 | Should not change between versions |
| Unanswerable | 6 | Plausible but absent from the corpus |

`questions.jsonl` holds one line per question: `id`, `category`, `document`, `question`, `reference_answer` (empty when unanswerable), `evidence_terms` (all must appear in one retrieved chunk) and `answer_terms` (each entry is a list of accepted alternatives). The owner reviews the questions and reference answers before the paid run.

### Arms

Both arms are identical except for the Extract `config_version`:

- **Source**: `existing_files` with all 9 corpus documents.
- **Extract**: `strategy: auto`, `ocr: {mode: auto, languages: ["eng"]}`, `tables: preserve`, `quality_policy: default-v1`; `config_version` is `layout-ocr-v1` in arm A and `layout-ocr-v2` in arm B.
- **Clean and Chunk**: the editor's defaults for a new pipeline, which means `section_token` with `add_heading_context: true`. **Embed**: the server's embedding settings. The exact values are written to the state file and the report.
- **Publish**: separate knowledge sets, "Extract A/B v1" and "Extract A/B v2".
- **Answer pipelines**: vector retrieval, `top_k: 5`, the default prompt template from `GET /pipelines/options`, `google/gemini-2.5-flash`, temperature 0, `max_tokens: 512`. The only difference between the two versions is the retriever's `index_id`.

### Measures

**Automatic, from the retrieved evidence:**

1. **Evidence hit@5**: at least one of the 5 retrieved chunks contains every `evidence_terms` entry (case-folded, whitespace-normalized). For table questions the terms include the column header, so a row without its header does not count.
2. **Evidence rank**: the position of the first matching chunk, reported as mean reciprocal rank.
3. **Fact present**: the answer contains an accepted alternative for every `answer_terms` entry. This is only a cross-check on the manual score.

**Manual, blind:**

- `score.py blind` writes `blind_review.csv`. For each question it lists the question, the reference answer and the two answers with their cited evidence, labelled X and Y. X/Y is assigned to v1/v2 at random per question, using a fixed seed, and the key is kept in `blind_key.json`, which is not opened until scoring is finished.
- Each answer gets one label:
  - **correct**: states the reference fact and nothing contradicting it.
  - **partial**: the right fact but incomplete, or with an unsupported extra claim.
  - **wrong**: a wrong or missing fact.
  - **correct-abstain**: an unanswerable question answered with `INSUFFICIENT_EVIDENCE`.
  - **wrong-abstain**: abstained on an answerable question.
  - **fabricated**: answered an unanswerable question.
- Each answer also gets **supported** (yes/no): every claim is backed by the evidence it cites.
- Scoring is done by Claude in this session. It is a model judgment too, so to limit bias: the arms are hidden, the rubric is fixed above, every label has a one-line reason, and the owner spot-checks at least 10 rows chosen at random. If the spot-check disagrees on more than 2 of the 10, the owner's labels decide and the rest are re-reviewed.
- `score.py final` reads `manual_scores.csv` and the key, and writes `report.md` and `per_question.csv`.

**Operational:** query latency, tokens and generation cost per arm, with unknown values reported as unknown, not zero.

Each question is paired: **win** (v2 correct, v1 not), **loss** (v1 correct, v2 not) or **tie**. "Correct" means `correct` or `correct-abstain`. Failed runs count as wrong and are listed. Nothing is dropped.

### Decision rule (fixed before the paid run)

"Affected" means the 28 questions in C1–C6. Net = wins − losses.

| Outcome | Condition | What we do next |
|---|---|---|
| **v2 helps** | Affected evidence-hit net ≥ +5, affected manual-correct net ≥ +3, control net ≥ −1 and unanswerable net ≥ −1 | Keep v2 as the default. Make the Extract panel simple (a separate spec). No further engine work until customer documents show a failure |
| **No real difference** | Both affected nets between −2 and +2 | Stop Extract engine work. Simplify the panel. Reconsider whether keeping v1 and v2 side by side is worth its cost |
| **v2 hurts** | Either affected net ≤ −3, or control net ≤ −2 | Investigate the per-question losses before any other Extract work |
| **Inconclusive** | Anything else | Inspect the mixed questions, report them, and let the owner decide. Do not add questions |

The corpus is built to expose known v1 defects. A "v2 helps" result therefore shows that v2 fixes those cases in real retrieval and answers; it does not prove an improvement on any particular customer's documents. The control documents check that v2 does not regress ordinary files.

### Cost

These are estimates. Prices come from the model catalog on 2026-10-07 (`google/gemini-2.5-flash` at $0.30 per million input tokens and $2.50 per million output tokens).

| Work | Estimate | Basis |
|---|---|---|
| Embeddings, both arms | < $0.01 | Under 60k tokens per arm with `text-embedding-3-small` |
| Answers | about $0.10 | 80 answers × about 3k input and 150 output tokens |
| **Total** | **about $0.10–0.20** | Hard cap: the script stops if the recorded total exceeds **$2** |

No paid model is used for scoring.

## Files

Scripts and data live under `backend/scripts/extract_ab/`, next to the existing `check_experiment_live.py`. They run inside the backend container, because this Windows machine has no host backend virtual environment, and the backend image does not mount the source, so the files are copied in with `docker compose cp`.

| File | Purpose |
|---|---|
| `make_corpus.py` | Writes the corpus and `corpus-manifest.json` (file names, SHA-256, target fix) |
| `questions.jsonl` | The 40 questions, reference answers and expectations |
| `run.py` | Stages `setup`, `preview`, `index`, `ask` and `fetch`; state in `state.json`; `--allow-paid` is required for `index` and `ask` |
| `score.py` | `blind` writes the review sheet and key; `final` writes the report |
| `README.md` | The exact commands and order |
| `backend/tests/test_extract_ab.py` | Tests for the generator and scoring |

## Implementation slices

### Slice 1: Corpus, questions and scoring (free)

- `make_corpus.py`, `questions.jsonl` and `score.py`.
- Tests:
  - The generator writes identical hashes on two runs.
  - Every evidence and answer term of an answerable question occurs in its document's source text.
  - Question IDs and question texts are unique.
  - Scoring handles normalization, table header terms, abstentions, failed runs (counted as wrong), missing answers (an error, never silently dropped), blind labelling with a fixed seed and the win/loss/tie pairing.
- **Done when** the tests pass and the owner has reviewed the questions and reference answers.

### Slice 2: Setup and free preview check

- `run.py setup`: creates the project "Extract A/B 2026-10", uploads the corpus, reads the embedding settings and editor defaults, and saves both ingestion pipeline versions (v1 through the API).
- `run.py preview`: runs ingestion previews (no embedding cost) for both versions and reports, for each answerable question, whether its evidence terms appear together in a v1 chunk and in a v2 chunk.
- **Done when** every v2 expected term set is found in a v2 chunk. If one is not, either the question is wrong or v2 has a defect. Fix the question, or record the defect, before any paid step.
- Report the preview result to the owner. It already shows how much v1 and v2 differ before anything is spent.

### Slice 3: Paid run (owner approval required)

- `run.py index --allow-paid`: runs both ingestions, waits for both indexes to be `succeeded`, and records the index IDs and processing runs.
- `run.py ask --allow-paid`: creates both answer versions, asks every question through both one at a time, polls each run, and enforces the cost cap.
- `run.py fetch` saves every query run as `answers.jsonl`.
- **Done when** all 80 runs have finished, each as succeeded, insufficient_evidence or failed.

### Slice 4: Score and record the decision

- `score.py blind`, then manual scoring into `manual_scores.csv`, the owner's spot-check, then `score.py final`.
- Copy `report.md`, `per_question.csv`, `answers.jsonl`, `blind_review.csv`, `manual_scores.csv`, `blind_key.json`, `corpus-manifest.json` and `state.json` (IDs only, no secrets) to `docs/qa/extract-ab-<date>/`.
- Apply the decision rule. Update this spec's status, `docs/implementation-plan.md` and the extract plan's "Deferred" section.

## Acceptance criteria

- Both indexes were built from the same 9 files (matching hashes) with identical settings except the Extract version, as shown in their pipeline versions.
- All 40 questions have a finished run for both arms, and failures are listed rather than dropped.
- Every answer has a manual label and a one-line reason, given before the key was opened, and the owner's spot-check is recorded.
- The report shows, per category and overall: evidence hit@5, MRR, manual correctness, supported rate, wins/losses/ties, query latency and costs (known sum, known count, total), the answer model and the run date.
- The decision follows the rule in this spec and is recorded in `docs/implementation-plan.md`.
- Recorded cost is at or below the $2 cap.

## Results (2026-10-07)

Full report, per-question results, raw answers and labels: `docs/qa/extract-ab-2026-10-07/`. Project `f0dae5b1…`; v1 index `01af9425…` (26 chunks), v2 index `61301c08…` (38 chunks), both from the same 9 files. Recorded generation cost: $0.0512 for 80 answers.

| Measure | v1 | v2 |
|---|---|---|
| Correct (blind labels), all 40 | 36 | 40 |
| Correct, 28 affected | 24 | 28 |
| Wins / losses / ties (correct) | | 4 / 0 / 36 |
| Evidence hit@5 in chunk text, 34 answerable | 23 | 24 |
| Evidence hit@5 counting the section path | 23 | 30 |
| Answers whose cited chunk supports subject and value | 21 | 24 |
| Unanswerable correctly declined | 6 / 6 | 6 / 6 |
| Mean query latency | 2,233 ms | 2,213 ms |

Nets: affected evidence +1, affected correct +4, control 0, unanswerable 0. The rule needs an evidence net of at least +5 for "v2 helps", and a correct net of at most +2 for "no real difference", so the result is **inconclusive**.

What the per-question inspection shows:

1. **v2 was never worse.** All four v1 errors are on targeted documents. Two of them (q03, q05) are the column-interleaving defect: v1 attributed a fact to the site in the neighbouring column and then declined to answer. The other two (q08, q09) are page-1 table rows that v1 failed to retrieve.
2. **v1 cannot publish this corpus with the default quality policy.** It rejects `service-rates.pdf` ("tables exceeded supported structural bounds") and the whole run fails. Both arms were therefore run with `warn-v1`, which changes only publication gating.
3. **v2's headings reach search but not the answer model.** The section heading is added to the embedded text only (`embedding_text`). The model receives each chunk's label and text (`generation.messages_for`), so a v2 handbook chunk reads "The notice period is 14 calendar days" without "Contractors". v2 still answered all six handbook questions correctly, because search ranked the right section first, but none of those answers is supported by the cited text. v1's larger chunks often include the part heading in their text.
4. **v2 creates heading-only chunks** ("Staff Handbook", "Part A: Employees"). They take retrieval slots and the model cites them as if they linked to a neighbouring chunk.
5. **A table that continues on a new page loses its header in both versions** (q10–q12). The model inferred the column meaning.
6. CSV rows have their header only in v2 (q25, q26).

Decision (owner instruction on 2026-10-07: "once you developed spec for improve go and develop it"): keep v2 as the default and stop new extraction work. Make the v2 structure reach the answer model, and simplify the Extract panel. Both are in [spec 0005](0005-section-context-and-simple-extract.md). Findings 4 and 5 are recorded there as later work.

## Owner decisions (2026-10-07)

- **D1. Scoring.** No LLM judge; `google/gemini-2.5-flash` is too weak for scoring. Answers are scored blind by Claude against the rubric, with an owner spot-check.
- **D2. Run approval.** The paid run (Slice 3) is approved after Slice 2's free check is reported.
- **D3. Real documents.** None added for this round.

## Out of scope

- Simplifying the Extract panel. That is a separate spec, decided by this result.
- Adding retrieval metrics, expected-evidence fields or manual scoring to the app. Do that only if this comparison shows they are worth having permanently.
- Adaptive DPI, OCR retries or any new extractor version.
- PPTX tables (not extracted by either version).
