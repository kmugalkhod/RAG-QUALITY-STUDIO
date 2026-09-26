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
2. Inspect Question, Retriever, Prompt, LLM and Answer. Select Retriever and use **Documents to search** to confirm the exact collection version. Edit labeled node forms rather than relying on canvas dragging. Set a bounded **Top k** and review prompt/model settings.
3. Enter a pipeline name and select **Save version**. The UI shows unsaved changes when the draft differs from the version. Select **Open Playground** to test the saved version.

Expected result: a numbered immutable answer version appears; **Pipeline test** uses that version unless you deliberately test a draft. If saving fails, inspect the validation panel, fix its node/field and retry. A missing ready index or model prevents execution. After a failed question run, inspect its status before another paid call. Continue with [answers and evidence](./evidence.md) and [versions](../concepts/versions.md). Arbitrary branching and executable code in nodes are unsupported by this template.
