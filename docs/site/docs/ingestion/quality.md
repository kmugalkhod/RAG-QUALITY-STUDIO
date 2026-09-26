---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Diagnose quality findings
slug: /ingestion/quality/
---

Find the specific extraction problem, correct the source, and verify that only the repaired, redacted version can be published. This is tutorial **T5**, using two reviewed fictional UTF-8 files. It tests a deliberate replacement character and a synthetic email; it does not claim OCR quality or complete sensitive-data detection.

## Prerequisites and fixture

Use an isolated project and download <a href="/examples/harbor-quality-corrupt.txt">the deliberately corrupt file</a> and <a href="/examples/harbor-quality-repaired.txt">the repaired file</a>. Their hashes and expected differences are in the <a href="/examples/README.md">fixture review</a>. Start the local stack and configure embeddings before the final run. Upload both under **Knowledge Base → Documents → Add document**; do not process/publish the corrupt file through the simple document path. The processing preview is local/source work; final embedding can be billed and dollar cost is unknown without provider pricing.

![Corrupt source fails a strict quality preview; a separate repaired source passes, redacts its email, and can be published by a saved run](/img/quality-repair.svg)

<a href="/img/quality-repair.svg">Open the repair diagram at full size</a>. In text: the failed draft is not published; a new document record with repaired source text is previewed under the same policy before a ready index is built.

## T5: reproduce and repair

1. Open **Pipelines → Ingestion pipelines → New ingestion pipeline**. In Source **Stage settings**, select only `harbor-quality-corrupt.txt`. Select **Extract** and, if the saved draft is legacy, **Enable robust extraction**. Set **Quality policy** to **Strict**. Open **Quality thresholds** and set **Maximum replacement-character ratio** to `0`; this intentionally rejects any replacement glyph in the synthetic file.
2. Select **Clean → Sensitive-data policy** and confirm **Redact sensitive values before chunking and embedding** with the `email` action set to **Redact value**. Select **Preview processing**, then **Inspect stages**. Read the item quality decision and the `replacement_character_ratio_high` finding. Compare **Extracted**, **Cleaned**, **Changes**, and **Chunks**. The cleaned text should show `[EMAIL]` rather than `sample@example.test` if that detector applies.

   ![Strict synthetic preview reports one quality failure before any index is published](/img/screenshots/09-quality-failure.png)

   <a href="/img/screenshots/09-quality-failure.png">Open the failed preview capture at full size</a>.

3. Do not publish the failed source. Return to the Source settings, deselect the corrupt document and select `harbor-quality-repaired.txt`. Keep the same strict threshold and sensitive-data policy. Select **Preview processing** again, then **Inspect stages**. Confirm the replacement-character finding is gone and the cleaned email remains redacted.

   ![Repaired synthetic file in the Cleaned preview stage with its fictional email replaced by the EMAIL marker](/img/screenshots/10-quality-repaired.png)

   <a href="/img/screenshots/10-quality-repaired.png">Open the repaired preview capture at full size</a>.
4. Select the Publish node, name a new collection, then **Save version**. Confirm the saved version number and select **Run ingestion**. Inspect each item and follow **Inspect published index** only if the run succeeded. Check that the published membership contains the repaired document, not the corrupt one.

Expected result in the isolated deterministic journey: the first preview has a quality failure and cannot be treated as a clean publication; the second preview passes the replacement-character check with `[EMAIL]` in cleaned output. A required failed item blocks an atomic run, while a separately marked optional item can be excluded only under its saved policy. A warning is distinct from a failure: **Warning publication** can block or publish with a visible warning, and **Failed optional items** can fail or exclude. Neither option changes the source text.

If the first preview unexpectedly passes, verify that **Strict** and threshold `0` are in the exact draft, confirm the file hash, then preview again. If the repaired file still fails, read the finding code and stage rather than relaxing the threshold just to make the run green. For OCR/page-origin failures, inspect [extraction](./extraction.md) and installed capability; for duplicate or language findings, inspect [cleaning](./cleaning.md). A protected Raw/Changes stage needs owner/admin access and retained encrypted artifacts. A failed or cancelled run does not publish a ready index; check its terminal state before another paid attempt. The current schema-v2 quality and redaction path is locally tested; external OCR and model behavior remain gated.
