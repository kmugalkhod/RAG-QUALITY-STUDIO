---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Build an Existing Files ingestion pipeline
slug: /ingestion/pipelines/
---

Preview a local source without publishing it, save an immutable ingestion version, then run it into a ready collection. This tutorial covers **Existing Files** only, at app commit `481b4eca90c5` plus documentation changes, reviewed 2026-09-26. Embeddings require configuration and may incur charges; no remote account is needed.

## Prerequisites

Start the [local stack](../start/install.md), configure [embeddings](../start/configure.md), and upload and [prepare harbor-desk.txt](../knowledge-base/prepare.md) in a new project. The Existing Files source selects document records in that project. Use this synthetic file to keep previews free of private content.

## Configure and preview

1. Open **Pipelines**, choose **Ingestion pipelines**, then **New ingestion pipeline**. Enter `Harbor files ingestion` under **Pipeline name**.
2. Keep **Existing Files** in **Source type** and select `harbor-desk.txt`. Open each node's labeled settings panel: Source → Extract → Clean → Chunk → Embed → Publish. The default graph is supported; unsupported edges and missing settings are rejected by the server.
3. Select **Preview processing** for the exact draft configuration. This one action discovers included/excluded source items and processes a bounded preview. Select **Inspect stages** on an item to inspect Raw, Extracted, Cleaned, Changes and Chunks where available. A preview does not publish or advance a ready pointer; it may store bounded preview artifacts.

Expected preview: one included local item with synthetic content and no ready index created by preview alone. If no file is selected, select the document and retry. If the preview expires or fails, refresh status and create a new preview. Processing settings and installed extraction capabilities can change the representation; inspect the item result rather than assuming a fixed chunk count.

![Raw and processed preview stages for the included synthetic Existing Files item](/img/screenshots/06-ingestion-preview.png)

## Save and execute

4. Select the Publish node and confirm its collection destination in the node settings before selecting **Save version**. Confirm the displayed saved version number. If validation fails, use the selected node's form to fix the named setting, then save again. A changed draft is not the previously saved version.
5. Select **Run ingestion**. The run uses the destination saved in that version; there is no separate destination form at this step. Inspect the durable run status and per-item outcomes. Follow **Inspect published index** into **Knowledge Base → Collections**. The run should cite the saved ingestion version and a ready immutable index only after all required work succeeds.

If the worker or embedding provider fails, refresh the run before retrying. A failed or cancelled run cannot publish a partial ready index. A request already sent to the provider may still incur cost. Correct settings, save a new version and run again; keep the previous ready index available. Continue with [preview inspection](./previews.md), [run details](./runs.md), [collection inspection](../knowledge-base/collections.md), or [source choices](./sources/index.md). External Website, S3, Notion and Confluence integrations require separate configuration and live account validation; this tutorial makes no claim about them.

![Saved Existing Files ingestion graph with every stage complete](/img/screenshots/07-ingestion-run.png)

![Successful run link to the exact ready index version](/img/screenshots/08-published-index.png)

These captures use an isolated local stack, fictional source text and deterministic provider transport; paid-provider and remote-account behavior remain unverified here.
