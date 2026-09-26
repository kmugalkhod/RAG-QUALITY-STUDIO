---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Test in the Playground
slug: /answers/playground/
---

Use the Playground to separate passage search from a generated answer. Start with a ready index in the current project. For **Pipeline test**, configure a server-side answer provider; generation can be billed. A retrieval-only test may still bill an embedding call in Vector or Hybrid mode.

## Search passages without an answer

Open **Playground → Retrieval test → Retrieval settings**. Select **Documents to search**, choose a **Search method**, enter a **Search query**, and select **Run retrieval test**. The result says **No answer was generated** and shows the index version, **Top k**, ranked passages and **View passage [rank]** controls. Inspect the passage text before deciding whether the answer model would have had enough evidence. Retrieval tests are transient; **Past questions** lists answer query runs, not these passage-only tests. See [retrieval settings](./retrieval.md) for method bounds and score meaning.

## Test a saved or draft answer pipeline

1. Select **Pipeline test → Pipeline settings**. Choose **Pipeline** and **Pipeline version**, or use a custom test. The panel says **Testing the saved version**, **Test draft · changes are not saved**, or **Custom test · no saved version**. Read that status before comparing outputs.
2. Confirm **Documents to search**, **Search settings**, **Prompt** and answer-model settings. A saved version pins its index and execution configuration. If the panel warns **Your pipeline is searching old data**, choose deliberately whether to keep that index or select **Test with current version [number]** in an unsaved draft.
3. Enter a **Question** and select **Run pipeline test**. Open **Sources & details** to see supplied passages, citation labels, the index version and the recorded request snapshot. Try an unanswerable question too; the answer should report insufficient evidence instead of inventing a citation.

Expected result: the completed answer and its evidence are inspectable together. The answer may vary with a live model. A citation means that the labeled passage was supplied to generation; it is not independent proof that the answer is true. A changed test draft does not become an immutable candidate until you explicitly save a new version. The current query path records completed, failed and insufficient-evidence runs, but does not stream tokens or expose query cancellation. See [Past questions](./history.md) to reopen saved answer results and [answer pipelines](./pipelines.md) to save a configuration.

If a test is disabled, check for a ready index, valid fields and provider configuration. On a failed run, read the safe error in **Sources & details**, then retry with a new question after correcting its cause. Do not infer zero cost from a missing dollar amount; usage can be known while pricing remains unavailable. This page reflects the local app and deterministic test transport; configured paid provider outcomes need separate verification.
