---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Run and inspect ingestion
slug: /ingestion/runs/
---

Execute an exact saved ingestion version and inspect durable progress, item outcomes and the published index link. The run records source selection, processing, embedding and destination; the previous ready index remains available if a new run fails.

## Prerequisites

Complete a [processing preview](./previews.md), configure embeddings, and select **Save version** after correcting all validation errors. The run button is disabled for an unsaved or dirty draft. A remote run may fetch pages/objects and an indexing run can send paid embedding requests, including an in-flight request after cancellation. The dollar amount depends on provider and source pricing.

## Run and read the result

1. In **Ingestion editor**, confirm **Saved version** and the Publish node's **Reusable index collection** or **New knowledge set name**. Choose **Run ingestion** for Existing Files/S3/Notion/Confluence, or **Collect source & publish index** for Website.
2. Follow the **Ingestion run progress** bar through discovering, processing and indexing checkpoints. Read the per-item page for new/changed/unchanged/removed, `ready`/succeeded/failed/excluded/cancelled, reason and chunk count. Select an item to inspect **Extracted and cleaned content** and protected stages where permitted.
3. On success, use **Inspect published index** to inspect the exact ready version and membership. If available, **Inspect source snapshot** opens the captured remote revisions; **Use in answer pipeline** selects the same ready index for a saved answer version.

Expected result: only required successful included items become members of a ready immutable index. A run reports its saved pipeline version and an exact source snapshot for remote collection. A preview alone never yields this link. The [Existing Files tutorial](./pipelines.md) exercises the full local path.

For a running job, **Cancel run** stops scheduling further work but may not interrupt a provider call already sent. On a failure, inspect the terminal run and item reasons before starting another run; correct settings in a new saved version or use an approved source refresh. Never infer that a partially populated index is ready. A stale/interrupted job is recovered by worker logic, not by deleting the project. See [quality findings](./quality.md), [source history](./source-history.md), and [collections](../knowledge-base/collections.md). This page covers locally tested job behavior; paid/live accounts remain conditional.
