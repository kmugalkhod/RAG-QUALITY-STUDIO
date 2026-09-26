---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Choose a source
slug: /ingestion/sources/
---

Choose the bounded source that matches the material you can access, then preview the exact draft before saving a version. The current Source node supports five kinds in schema-v2 ingestion; availability depends on server configuration and source permission.

## Prerequisites and choice

Create a project and open **Pipelines → Ingestion pipelines → New ingestion pipeline**. Select the Source node on the canvas, then use its keyboard-accessible **Stage settings → Source type** field. No remote source is required for **Existing files**; upload a fictional file first as in the [first workflow](../../start/first-workflow.md).

| Source type | Input and discovery | Gate |
| --- | --- | --- |
| **Existing files** | Explicit document records already in this project; schema-v2 can prepare a new or failed upload at run time. | Local stack; embeddings for publication. |
| **Website** | Public HTTP(S) pages selected by one URL, a list, a crawl, or a sitemap; origin and fetch budgets apply. | Public reachable source; live network behavior requires separate acceptance. |
| **Amazon S3** | Objects under a selected bucket and optional prefix, filtered by selected file types. | Enabled [vault](../connections.md), scoped read account, live permission check. |
| **Notion** | Pages shared with an integration, explicit page IDs, or data source IDs. | Enabled vault, shared integration, live permission check. |
| **Confluence** | Accessible current pages, explicit spaces, or explicit page IDs. | Enabled vault, scoped account, live permission check. |

Change **Source type** in an unsaved draft and inspect the new fields. Enter only an allowed public URL or select a saved connection. Select **Preview processing**; read each item's included/excluded reason, canonical location and processing state. The preview checks the draft and does not create a ready index. See [preview processing](../previews.md) before **Save version** and [run inspection](../runs.md) before repeating a failed run.

Expected result: the selected source's labeled settings appear and the server either returns a bounded item preview or an actionable validation/availability error. If a credentialed kind says **setup required**, use [Settings](../connections.md). If a Website target is blocked, keep its safety limits and choose a public, permitted origin; loopback/private URLs are not valid workarounds. Embedding, query and evaluation charges are separate from source collection; dollar cost is unknown without the configured provider's pricing. Source kinds are implemented and deterministically tested at the verified commit, while a reader's live account and public host remain unverified here.
