---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: How the workflow works
slug: /concepts/workflow/
---

Trace a document from upload to a cited answer and identify where versions and charges arise. Applies to the current local application at commit `481b4eca90c5`, reviewed 2026-09-26. Model operations require configuration; the diagram is a synthetic example.

![Source-to-answer workflow with immutable version boundaries](/img/workflow.svg)

## Follow one record

Prerequisite: one project in the [local app](../start/install.md). Open **Knowledge Base → Documents** and add <a href="/examples/harbor-desk.txt" download>harbor-desk.txt</a>. Upload stores the source document. **Start processing** creates a processing run and versioned chunks. **Collections → Publish prepared documents** creates a new index version from selected prepared content only after embeddings succeed. **Use version 1 in a pipeline** selects a specific ready index for the Retriever node. **Save version** fixes answer settings; **Run pipeline test** stores a query run with the evidence supplied to the model.

## Read the boundaries

Processing, indexing, querying and evaluation are separate operations. A preview is inspection of a draft, not publication. A failed or cancelled index is not **Ready**. Retrieval results have rank and distance/score semantics; they are not a probability of truth. The answer may still be wrong even when it cites a passage. An ingestion pipeline can collect remote source revisions, but those connectors require their own configured connection and, for external accounts, live acceptance.

Expected result: the selected collection version and saved answer version remain inspectable alongside the run. If any stage stalls, inspect its status before starting another paid operation. Continue with [versions](./versions.md), [collections](../knowledge-base/collections.md), or the [first workflow](../start/first-workflow.md).
