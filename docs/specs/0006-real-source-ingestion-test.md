# 0006. Real-source ingestion test and settings verdict

**Date**: 2026-10-09
**Status**: Approved by the owner on 2026-10-09: websites plus real files, retrieval checks plus blind answer scoring, $1 spending cap. Run and reported on 2026-10-09; results in `docs/qa/real-source-2026-10/`.

## Summary

Every earlier Extract measurement used synthetic documents we wrote ourselves. This test ingests real public content, four websites and three real files, into real indexes, checks how well the content is structured and retrieved, and repeats the run several times with one group of settings changed per round. The result is one Excel workbook that records what was ingested, how satisfactory the result was, which settings were used in each round and, for every setting, whether it should stay visible, stay under Advanced or be removed.

No application code changes in this spec. A defect found during the test is recorded and fixed in a separate slice.

## Sources

| ID | Source | Shape it tests | Licence | Scope |
| --- | --- | --- | --- | --- |
| W1 | Python tutorial, `docs.python.org/3/tutorial/` | Technical docs, code blocks, nested headings | PSF documentation licence | Crawl, depth 1, at most 20 pages |
| W2 | Wikipedia articles, `en.wikipedia.org/wiki/…` | Long articles, data tables, infoboxes | CC BY-SA 4.0 | URL list of about 10 chosen articles |
| W3 | GOV.UK guidance, `www.gov.uk/…` | Plain policy text, steps, lists | Open Government Licence v3.0 | URL list of about 10 guidance pages |
| W4 | MDN Web Docs, `developer.mozilla.org/en-US/docs/…` | Reference pages with tables and code | CC BY-SA 2.5 | URL list of about 10 pages |
| F1 | A two-column research paper (arXiv PDF) | Two-column reading order, headings, references | Licence recorded per paper; open licence preferred | 1 file |
| F2 | A government statistical or annual report (PDF) | Real tables that span many rows and pages | Open Government Licence or public domain | 1 file |
| F3 | A scanned public-domain document (image-only PDF) | OCR, rotation, scan quality | Public domain | 1 file |

- Websites are fetched by the product's Website connector, which honours robots.txt and its page, depth and speed limits. Each website is fetched **once**; later rounds reuse the saved source snapshot, so every round sees exactly the same pages and no site is crawled repeatedly.
- Files are downloaded once to a folder outside the repository and uploaded to a dedicated project. Their URLs, licences and SHA-256 hashes are recorded; the files themselves are not committed.
- All data goes into a new dev project, "Real-source test 2026-10". Nothing touches the owner's other projects.

## Rounds

Each round is a saved pipeline version and its own published index. Only the named settings change; everything else stays at the recommended values from spec 0005 (`recommendedExtractSettings`) and section-aware chunks of 600 target, 800 maximum and 80 overlap tokens.

| Round | Applies to | Change | Question it answers |
| --- | --- | --- | --- |
| R1 | All sources | Recommended settings (v2) | Baseline: is the default good enough on real content? |
| R2 | Files | Extractor `layout-ocr-v1` | Does v2 matter on real files? |
| R3 | Files | OCR resolution 300 DPI and maximum OCR pages 100; then OCR off | Do the OCR settings change anything a user would notice? |
| R4 | Files | Table evidence "Plain text" | Does the table format matter for retrieval? |
| R5 | Websites | "If a file can't be read well" → publish the others and show warnings | Does the stop rule block real crawls? |
| R6 | All sources | Chunks of 300 target / 400 maximum / 40 overlap | Is chunk size more important than any Extract setting? |

R6 is included because chunk size is the setting most likely to change retrieval; it tells us whether Extract settings deserve attention at all by comparison.

## What is measured

**Ingestion and structure (free, from previews and runs):** pages and files discovered, included, excluded and failed, with reasons; quality decisions and findings; block types (headings, paragraphs, lists, tables, code); share of body blocks with a heading path; table blocks with header rows; OCR pages and confidence; chunk count and token sizes; run time.

**Retrieval (deterministic, no model judge):** about 8 questions per source, about 56 in total, including one question per source whose answer is not in the source. Each question is written from the source page itself, before looking at the extracted output, together with a short answer phrase that must appear in the correct chunk. For every round: hit@1 and hit@5 (the answer phrase is in the top 1 or top 5 retrieved chunks), the rank of the first hit, and, for the unanswerable questions, the top score for reference.

**Answers (paid, scored blind):** 20 questions, spread over all sources, are answered end to end in R1 and in R2. Answers are scored by Claude against the spec 0004 rubric with the rounds hidden (`correct`, `correct-abstain`, `partial`, `wrong`, `wrong-abstain`), each label with a one-line reason, and the owner spot-checks 10 rows. No LLM judge is used.

**Satisfaction per source and round:** **Good** when hit@5 is at least 90%, no required file failed and structure checks pass; **Acceptable** when hit@5 is at least 75%; **Poor** otherwise. The rule is fixed now, before any result is seen.

## Settings verdict

For every Extract setting, and for chunk size, the workbook records the default, the rounds that changed it, the measured difference and one of:

- **Keep visible**: changing it made a difference an ordinary user should decide on.
- **Keep in Advanced**: it made a difference only in specific cases (for example small print or long scans).
- **Candidate to remove**: changing it made no measurable difference on any source.

A verdict of "candidate to remove" is a recommendation for a later spec, not a change made here.

## Workbook

`docs/qa/real-source-2026-10/real-source-test.xlsx`, with one sheet each for:

1. **Summary**: satisfaction per source and round, total cost, the recommendation.
2. **Sources**: ID, URL, type, licence, pages or file hash, fetch date.
3. **Runs**: round, source, every setting used, status, counts, time, cost.
4. **Structure**: per source and round, the structure measures above.
5. **Retrieval**: per question and round, expected phrase, hit@1, hit@5, first-hit rank, top chunk excerpt.
6. **Answers**: the 20 blind-scored answers with labels and reasons.
7. **Settings verdict**: per setting, default, change tested, measured effect, verdict.

The workbook is generated by a script from the saved results, so it can be regenerated; the raw results (JSON and CSV) are kept next to it.

## Cost and safety

- Paid steps (embedding and answers) run only with an explicit `--allow-paid` flag and stop when the recorded cost reaches **$1**. Expected total is about $0.50: embeddings about $0.02 per round, answers about $0.05 per answered round.
- Unknown cost is reported as unknown, not zero.
- Crawls stay within the limits above, at the connector's default speed of 2 requests per second.
- The answer model and embedding model are the ones already configured in the dev stack; both are recorded in the workbook.

## Slices

1. **Sources and free checks.** Choose the exact pages and files, record licences and hashes, create the project, fetch each website once, upload the files, run the R1 preview, and write the questions with answer phrases. Report the structure measures before any paid step.
2. **R1 paid run.** Index R1, run the retrieval checks and answer the 20 questions. Report R1 satisfaction.
3. **R2–R6.** Index each round from the same snapshots and files, run the retrieval checks, answer R2's 20 questions, score all answers blind, and ask the owner for the spot-check.
4. **Workbook and verdict.** Generate the workbook, write the settings verdict and recommendation, and record the result in `docs/implementation-plan.md`.

## Out of scope

- Changing any default or removing any setting. That follows in its own spec, based on the verdict.
- Crawling more than the pages listed in Slice 1, or any site that disallows it in robots.txt.
- Committing downloaded website content or files to the repository.

## Result (2026-10-09)

Results, the workbook and the settings verdict are in `docs/qa/real-source-2026-10/`. Two deviations from the plan, both decided before any paid round: the free R1 preview showed the recommended quality setting blocks the Census report, so R1 kept the recommended setting (and failed for files, as a user would see) and a files baseline **R1w** ("Publish the other files and show warnings") was added for R2-R4 and R6; and the file answers were compared between R1w and R2, because R1 published no file index. Total cost was about $0.20 of the $1 cap. The three high-severity findings (X1-X3) and the settings verdict are follow-up specs; nothing in the product was changed here.
