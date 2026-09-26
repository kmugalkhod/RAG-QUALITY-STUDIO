---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Collections and index versions
slug: /knowledge-base/collections/
---

Publish a prepared document into a ready, immutable search corpus and inspect its membership. Applies to the current local app at commit `481b4eca90c5`, reviewed 2026-09-26. Publication embeds text and may incur provider cost.

## Prerequisites

At least one successful [processing version](./prepare.md) and [configured embeddings](../start/configure.md). The embedding model and vector dimension must match the selected index. A failed or partial index is unavailable for retrieval.

## Publish and inspect

1. Open **Knowledge Base → Collections** and select **Publish prepared documents**. Wait for the **Uploaded documents** collection to appear. If the button is disabled, inspect **Settings → Embeddings**.
2. Open the collection. Confirm **Ready**, **Current**, and its version number. Use **Sources** to check included prepared documents; **Versions** shows historical versions; **Passages** shows stored records.
3. Use **Test retrieval** with `When is Harbor Desk open?` and inspect returned passage text, rank and cosine distance. Distance is a search measure, not confidence in the answer.
4. Select **Use version 1 in a pipeline** using the actual displayed version number when ready to ask a question.

Expected result: the collection version remains fixed and its included content is inspectable. Publication only moves the current pointer after success. If the run fails, refresh the collection status, resolve the provider or document issue and start a new publication; do not query a failed version. If zero passages appear, revisit [document preparation](./prepare.md). Continue with [answer pipelines](../answers/pipelines.md) or [evidence](../answers/evidence.md). Live model reachability was not established by deterministic tests.
