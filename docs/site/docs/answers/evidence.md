---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Ask questions and inspect evidence
slug: /answers/evidence/
---

Separate passage retrieval from generation and check which evidence actually reached the answer model. Applies to the current Playground at commit `481b4eca90c5`, reviewed 2026-09-26. Embedding and generation calls may be billed; deterministic test answers do not verify a live provider.

## Prerequisites

A [ready collection](../knowledge-base/collections.md) for retrieval; a configured answer model and [saved pipeline](./pipelines.md) for a full answer. Use <a href="/examples/harbor-desk.txt" download>harbor-desk.txt</a> for the question below.

## Inspect a run

1. Open **Playground** and choose **Retrieval test**. In **Documents to search**, select the ready collection version. Enter `When is Harbor Desk open?` under **Search query**, then select **Run retrieval test**. This shows passages without generating an answer.
2. Choose **Pipeline test**. Confirm the saved pipeline name and version in the toolbar, enter the same text under **Question**, and select **Run pipeline test**.
3. Select an inline citation or **Sources & details**. Inspect the source label, supplied passage, rank and score/distance semantics. Open **Answer details** for version and run information; **Past questions** reopens prior runs.

Expected result: the cited passage includes Monday–Friday 09:00–17:00. A citation is valid only when it points to evidence supplied to the model. Similarity/distance is not answer confidence. Try a question absent from the source to inspect **Insufficient evidence** behavior; live model wording may vary. If the index is unavailable, choose a ready version; if a model call fails, inspect **Past questions** before retrying. Continue with [the first workflow](../start/first-workflow.md) or [API patterns](../api/patterns.md). Grounding is inspectable, not a guarantee of factual correctness.
