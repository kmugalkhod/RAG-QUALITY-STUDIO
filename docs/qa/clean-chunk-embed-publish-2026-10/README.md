# Clean, Chunk, Embed and Publish Index: baseline, 2026-10-17 (spec 0012, Slice 0)

Everything here is free: no provider request was made. Raw numbers are in
[`baseline.json`](baseline.json) and [`preview_timings.json`](preview_timings.json).
The scripts are in `backend/scripts/clean_chunk/`:

- `baseline.py` reads stored chunks, block spans and run stage states from the database (read only).
- `preview_timings.py` previews files through the API and reports each item's stage timings.
- `perf.py` times the Part C slow paths on synthetic input and prints an output digest, so a later run can show the output did not change.

## Stage timings of real runs (`ingestion_run_nodes`)

| Run | Pages | Chunks | Source | Extract | Clean | Chunk | Embed | Publish | Total | Embedding cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W1a, Python tutorial, recommended settings (2026-10-17 07:49) | 53 | 469 | 11.0 s | 0.04 s | 0.02 s | 4.0 s | 71.6 s | 4.8 s | 91.4 s | $0.0015 (74,728 tokens) |
| S6, 353 pages (2026-10-17 08:58) | 353 | 1,151 | 682.4 s | 0.05 s | 0.02 s | 21.8 s | 173.4 s | 3.1 s | 880.7 s | $0.0032 (157,642 tokens) |

Stage states only move forward. A Website run processes its pages after the crawl, and the first page moves the run through Extract and Clean to Chunk, so the extraction, cleaning and chunking of every page is counted under Chunk; the Extract and Clean rows only mark the transition. Embedding is the largest stage after fetching: 78% of W1a. The embed stage includes waits for the local request budget.

## Preview of the spec 0006/0008 files (`preview_timings.py`)

The seven files, recommended settings (`layout-ocr-v5`, structure-aware cleaning, `section-token-v2`), one preview: 196 s wall time, 185 s of known compute.

| File | Extract | Clean | Chunk | Chunks |
| --- | ---: | ---: | ---: | ---: |
| BERT paper (16 pages) | 5,065 ms | 35 ms | 163 ms | 133 |
| Census P60-279 (62 pages) | 24,913 ms | 90 ms | 277 ms | 517 |
| Surveyor VI scan (10 pages, OCR) | 27,081 ms | 5 ms | 53 ms | 23 |
| Eurostat key figures (French) | 56,653 ms | 97 ms | 304 ms | 394 |
| USGS Circular 115 scan (OCR) | 69,763 ms | 12 ms | 105 ms | 55 |
| DfT report template (DOCX) | 0 ms | 7 ms | 124 ms | 60 |
| Prevent slides (PPTX) | 0 ms | 0 ms | 58 ms | 15 |

Extraction is 99% of the processing time. Today every Clean edit changes the shared extraction-and-cleaning hash, so it repeats all of it, including about 97 s of OCR (C5).

## Chunk statistics of saved indexes (`baseline.py`)

Sizes are UTF-8 bytes of the passage text (embedding texts add the heading prefix). A passage "starts mid-word" when its first span starts inside a block with a letter or digit on both sides of the cut (an overlap start or a hard split).

| Index | Chunker | Passages | Median | Min | Max | Max embedding text | Under 40 bytes | Over 8,191 | Mid-word starts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A4s files F1-F3 | section-token-v2 | 673 | 651 | 12 | 800 | 1,102 | 6 | 0 | 156 (23%) |
| A4s files F4-F7 | section-token-v2 | 524 | 283 | 5 | 800 | 980 | 20 | 0 | 79 (15%) |
| A4s d2 | section-token-v2 | 790 | 559 | 1 | 800 | 1,031 | 30 | 0 | 164 (21%) |
| A4p files F1-F3 (children) | parent-child-v2 | 1,905 | 294 | 4 | 320 | 628 | 21 | 0 | 311 (16%) |
| A4p files F4-F7 (children) | parent-child-v2 | 937 | 225 | 4 | 320 | 504 | 34 | 0 | 157 (17%) |
| A4p d2 (children) | parent-child-v2 | 1,914 | 269 | 1 | 320 | 540 | 70 | 0 | 332 (17%) |
| Websites, spec 0006 round A1 | section-token-v1 | 2,381 | 605 | 6 | 800 | 937 | 41 | 0 | 674 (28%) |
| W1a Python tutorial | section-token-v2 | 469 | 616 | 15 | 800 | 893 | 2 | 0 | 137 (29%) |

Parents of the parent-child indexes: 612, 438 and 647, median 757 bytes, smallest 2 to 5 bytes. No saved index has an embedding text over the limit, because all of them use the recommended sizes. The limit is only reached by custom sizes, which validation accepts today (A8).

## Part C timings on synthetic input (`perf.py`, test image, this machine)

| Item | Input | Time | Output digest |
| --- | --- | ---: | --- |
| C1 chunking | one 2 MB paragraph of 71-character sentences, `section-token-v1` | 2.79 s | `a5f16cfe47b70341` |
| C1 chunking | the same, `section-token-v2` | 2.79 s | `a5f16cfe47b70341` |
| C2 cleaning | 1,000 pages × 20 blocks, structure-aware | 3.10 s | `778c4082f7f1b1c8` |
| C3 control characters | one 2 MB block | 0.21 s | `0408d18a63b95a23` |

The spec quotes 11.7 s for C1 and 0.64 s for C3 from the audit. The audit used a different input, and the numbers here are the ones Slice 5 is measured against.

## Part C after Slice 5 (2026-10-18)

The same `perf.py` on the code before this spec (`2f5851d`) and after Slice 5, in the test image on this machine. Every output digest is identical before and after.

| Item | Before | After | Output digest |
| --- | ---: | ---: | --- |
| C1 chunk one 2 MB block, `section-token-v1` | 2.72 s | 0.30 s | `a5f16cfe47b70341` |
| C1 chunk one 2 MB block, `section-token-v2` | 2.62 s | 0.21 s | `a5f16cfe47b70341` |
| C2 clean 1,000 pages × 20 blocks | 3.03 s | 1.28 s | `778c4082f7f1b1c8` |
| C2 build and validate 1,000 pages × 20 blocks (found while profiling) | 30.48 s | 0.68 s | `99e40c5922da71c6` |
| C3 control characters, 2 MB of ordinary text | 0.22 s | 0.002 s | `9c23deec8262b6ec` |
| C3 control characters, 2 MB with one every few words | 0.21 s | 0.26 s | `0408d18a63b95a23` |
| C4 fingerprints of 200 pages, peak traced memory | 27.0 MB | 0.3 MB | `b4b3732cb41480b1` |

The C2 "build and validate" row is the document check that every page's block IDs belong to the document; it rebuilt a set for each page block, so every extracted and cleaned document paid pages × blocks. C3 is a little slower only on text that is mostly control characters; ordinary text, which has none, is a hundred times faster.

Embedding (C6), from the opt-in `tests/test_indexing_throughput.py` with a deterministic provider double, so it measures database and batching cost, not provider latency:

| Index | Before | After |
| --- | --- | --- |
| First index, 2,000 chunks | 125 batches, 8.24 s | 32 batches, 1.11 s |
| Second index, 4,000 chunks (half reused) | 250 batches, 19.12 s | 63 batches, 2.91 s |

C5: a Clean-only change starts a processing run that reuses the earlier run's extracted document; the test replaces the extractor with one that fails if called, and the run succeeds with the same extracted output and a different cleaned output. The dev database's 616 existing schema-v2 processing runs were backfilled, so they are reusable at once.

## Part D new versions on the saved corpus (Slice 6, 2026-10-18)

Free and read-only: `backend/scripts/clean_chunk/v3_corpus.py` rebuilds every processing run of the eight saved indexes from its stored extracted and cleaned derivations, chunks and cleans again in memory and compares; raw numbers are in [`v3_corpus.json`](v3_corpus.json). `short_passages.py` gives the reason for each v3 passage still under 40 bytes.

**v1 and v2 are byte-identical.** All 94 runs give exactly their stored passages (text, embedding text, role and parent) when chunked again with their saved version (`section-token-v1` for the 47 web-A1 pages, `section-token-v2` and `parent-child-v2` for the rest). Cleaning the stored extracted document again with `structure-clean-v1` reproduces the stored cleaned output hash for all 30 file runs and all 64 website pages.

**v3 against the saved version, same sizes:**

| Index | Passages | Under 40 bytes | Of which on a page under 40 bytes | Mid-word starts | Median | Max embedding text | Parents (smallest) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A4s files F1-F3 | 673 → 660 | 6 → 1 | 1 | 156 → 0 | 651 → 656.5 | 1,102 → 1,094 | |
| A4s files F4-F7 | 524 → 506 | 20 → 5 | 4 | 79 → 0 | 283 → 301.5 | 980 → 953 | |
| A4s d2 | 790 → 751 | 30 → 2 | 0 | 164 → 0 | 558.5 → 583 | 1,031 → 1,026 | |
| A4p files F1-F3 (children) | 1,905 → 1,955 | 21 → 3 | 1 | 311 → 0 | 294 → 295 | 628 → 620 | 612 (4 bytes) → 630 (12) |
| A4p files F4-F7 (children) | 937 → 905 | 34 → 7 | 4 | 157 → 0 | 225 → 235 | 504 → 504 | 438 (5) → 423 (21) |
| A4p d2 (children) | 1,914 → 1,857 | 70 → 9 | 0 | 332 → 0 | 268.5 → 271 | 540 → 540 | 647 (2) → 618 (40) |
| Websites, round A1 (v1 → v3) | 2,381 → 2,334 | 41 → 0 | 0 | 674 → 0 | 605 → 608 | 937 → 937 | |
| W1a Python tutorial | 469 → 462 | 2 → 0 | 0 | 137 → 0 | 616 → 617.5 | 893 → 892 | |
| **All** | **9,593 → 9,430** | **224 → 27** | **10** | **2,010 → 0** | | | |

No v3 passage or parent starts mid-word, and no passage is larger than the saved maximum. 27 passages remain under 40 bytes, each where joining it would break another rule:

- 10: the page holds under 40 bytes ("(Blank Page)", a chapter divider such as "Population et société 1"). A passage cites one page, so it cannot join the next page.
- 11: a heading directly before, or a page number directly after, a table, list or code block that fills a passage ("Table 8-1 Authenticator Threats", "Head of Household"). Those blocks are never split, and the passage maximum is a hard limit.
- 2: both neighbours on the page are full ("Page 4 GAO-23-900494", a running footer read as a heading).
- 4: parent-child headings that the parent level joins to the parent before them while their text starts the next parent ("A.3 Fine-tuning Procedure").

So the Slice 6 check "no chunk under 40 bytes" holds for both website indexes and for every short passage that has room next to it, not for these 27. Removing them would mean crossing pages, splitting tables or lists, or exceeding the maximum, which v3 does not do.

**`structure-clean-v2` on the website pages.** Pages are grouped by host to measure repeated chrome, as a crawl groups them by source. On the 47 round-A1 pages, v1 removed 179 blocks as repeated site chrome, 4 of them protected (tables, lists, code, quotes or footnotes); v2 removes 162 and no protected block, keeping 19: those 4 protected blocks on every page and the first page's copy of each other repeat. The W1a pages have no repeated chrome under either version. The soft-hyphen case is covered by `tests/test_structure_cleaning_v2.py`: v1 kept a repeated line on every page because its fingerprint had a soft hyphen; v2 removes it from all pages except the first.

## Bug reproductions

One failing test per Part A item that has a backend or frontend path. Each states the fixed behaviour and is marked as expected to fail: `backend/tests/test_spec0012_repro.py` (strict `xfail`) and `frontend/tests/features/ingestion-pipelines/spec0012Repro.test.tsx` (`test.fails`). The slice that fixes an item removes its marker. Each was checked to fail on its assertion, not on setup: the backend tests against the unmodified code with `--runxfail`, the frontend tests by running a copy as plain tests.

| Item | Backend | Frontend | Fails today because |
| --- | --- | --- | --- |
| A1 | new index with an existing name | switching back to "new" | the save returns 201; the name field keeps "Docs" |
| A2 | | new draft's index name | it is "Ingested knowledge" |
| A3 | concurrent start | | the second start raises `IntegrityError` (served as 503) |
| A4 | stale-failed run | | the Extract stage stays `running`, the item stays `processing` |
| A5 | unpublished index | failed branch | the failed index's ID and version are returned; the strip shows "· version 3" |
| A6 | error after the index went live | | the run fails although its index is current |
| A7 | case-insensitive resolution and save | | "docs" creates a second index next to "Docs"; "DOCS" saves |
| A8 | 16,384 and 8,191 maximum | | both save |
| A9 | 15-minute throttling cap | | the index is still `queued` after 16 minutes |
| A10 | wait reason | | the run has no `waiting_reason` |
| A11 | usage after a cancel | cancelled run strip | tokens stay 0; the strip shows no usage |
| A12 | | stale embedding model | there is no "Use the server's embedding settings" button |
| A13 | one Chunk error | Chunk field mapping | the save reports 35 errors; no field key |
| A14 | v1 chunker record | | `processing_versions` has no saved config version |
| A15 | | character-window defaults | the window starts at 1,000/100, not the capability's 800/120 |
| A16 | | Undo after switching method | there is no Undo |
| A17 | | literal text box | "Page 1 of \n" becomes "Page 1 of" while typing |
| A18 | | Preserve structured blocks | it has an on/off toggle |
| A19 | | new literal step | it saves "Replace this literal" |
| A20 | plain error names | Clean field mapping | the message is buried in union errors; no field key |
| A21 | dehyphenation count | | a kept compound is counted (2 instead of 1) |
| A22 | | guided cleaner choice | "Compatibility cleaner" is offered |
