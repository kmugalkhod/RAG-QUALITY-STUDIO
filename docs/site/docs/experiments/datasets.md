---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Import reviewed questions
slug: /experiments/datasets/
---

Import a fixed question set before comparing saved answer pipelines. Use an isolated project and review every answerable and unanswerable question yourself. For tutorial T4, download the fictional <a href="/examples/orchard.txt">orchard source</a> and <a href="/examples/orchard-reviewed.csv">reviewed CSV</a>; hashes and intended results are in the <a href="/examples/README.md">fixture review</a>. Publishing the source needs configured embeddings and may incur cost.

## Preview, import and version

1. Open **Experiments → Dataset → Import a reviewed CSV**. You can first select **Download example CSV** to inspect the current two-column shape. T4's reviewed file has a different, deliberately unanswerable second row.
2. Enter **Dataset name**, leave **Version destination → Create a new dataset**, select **CSV file**, then select **Preview CSV**. Confirm each question and reference in the preview table. Empty `reference_answer` means no reference was supplied; it does not mean the correct answer is empty.
3. Resolve every row error, then select **Import reviewed dataset**. Confirm **Dataset version** now names version 1 and use **Inspect [count] dataset questions** to recheck the immutable rows. To correct a dataset later, import a new version under **Version destination → New version of [name]**; existing experiments retain their old version.

Expected result for `orchard-reviewed.csv`: two questions appear; the apple question has a reference, while the launch-code question has none. The parser requires UTF-8 CSV with a `question` header and optionally `reference_answer`, in either order, without extra columns. Questions must be 1–4,000 characters and references at most 12,000; the running server exposes its row and byte limits in the form. Import checks the previewed content hash and rejects a file changed afterward with 409.

If **Preview CSV** reports row or header errors, correct the file and preview again. If import reports that the file changed, preview the selected bytes again before retrying. A dataset is a human-reviewed input, not proof that its references are true; hold out questions that were not used to tune candidates. No evaluator or answer provider is called during preview/import. This schema and local import path are tested; live model outputs remain a separate gate. Continue with [run experiments](./runs.md), [metric requirements](./metrics.md), and [version provenance](../concepts/versions.md).
