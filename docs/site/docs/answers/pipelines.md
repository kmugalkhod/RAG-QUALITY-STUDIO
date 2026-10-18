---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Save an answer pipeline
slug: /answers/pipelines/
---

Bind an answer graph to a specific ready collection version and save its configuration. Applies to the current five-node answer template at commit `481b4eca90c5`, reviewed 2026-09-26. Saving is local; running the graph can make paid model calls.

## Prerequisites

Complete [collection publication](../knowledge-base/collections.md), with an embedding-compatible **Ready** index, and configure an answer model. The selected index determines which passages the Retriever may see. Content in retrieved passages is untrusted source data, not instructions to the model.

## Save and test

1. In **Knowledge Base → Collections**, open a ready version and select **Use version 1 in a pipeline** using the displayed number. Alternatively open **Pipelines → Answer pipelines → New answer pipeline**.
2. Inspect Question, Retriever, Prompt, LLM and Answer. Select Retriever and use **Index to search** to confirm the exact collection version. Edit labeled node forms rather than relying on canvas dragging. Set a bounded **Top k** and review prompt/model settings.
3. Enter a pipeline name and select **Save version**. The UI shows unsaved changes when the draft differs from the version. Select **Open Playground** to test the saved version.

## Optional rerank step

Select Retriever and choose **Add a rerank step** to insert a **Rerank** node between Retriever and Prompt. A chat model from your approved list reads the question with the retrieved candidates, as untrusted text, and returns their order; it does not write or score answers. The Prompt receives the first **Passages kept** (default 5, at most 20) in that order. With the step present, the Retriever's **Top k** is the number of candidates it reads: 30 by default and at most 50. If reranking fails, the retriever's order is used and the run says "Reranking failed; retriever order used". **Answer details** shows the step's model, time and its own cost, and **Sources** shows each passage's rank and its retriever rank. **Remove rerank step** reconnects Retriever to Prompt and sets **Top k** to the passages that were kept. Saving with the step creates an answer graph of schema version 3; earlier versions keep running exactly as saved.

Expected result: a numbered immutable answer version appears; **Pipeline test** uses that version unless you deliberately test a draft. If saving fails, inspect the validation panel, fix its node/field and retry. A missing ready index or model prevents execution. After a failed question run, inspect its status before another paid call. Continue with [answers and evidence](./evidence.md) and [versions](../concepts/versions.md). Arbitrary branching and executable code in nodes are unsupported by this template.
