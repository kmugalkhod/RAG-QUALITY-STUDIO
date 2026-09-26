---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Notion source
slug: /ingestion/sources/notion/
---

Select a bounded set of pages visible to a Notion integration and inspect their extracted text before indexing. The connector is deterministically tested; this guide does not assert that any reader's live Notion workspace has been checked.

## Prerequisites and scope

Use a read-only test integration explicitly shared with the pages or data sources you intend to collect. Save it in the local encrypted [source vault](../connections.md) and select it in a schema-v2 ingestion draft. Have an embedding provider for publication; provider and Notion API usage may be billed under your own terms. Never paste an integration token into the Source node or docs URL.

1. Open **Pipelines → Ingestion pipelines → New ingestion pipeline**, select the Source node, choose **Notion** under **Source type**, and choose **Notion connection**.
2. Under **Discovery scope**, choose **All pages shared with integration**, **Explicit page IDs**, or **Data source IDs**. For explicit modes, enter one UUID per line. Prefer a small explicit scope for the first run.
3. Set **Maximum pages**, **Maximum API requests**, **Blocks per page**, **Maximum block depth**, **Text characters per page**, and timeout. Select **Preview processing** and inspect each included, excluded or failed page and its available provider revision. Then **Save version** and **Run ingestion**.

Expected result: the preview contains only content visible to that integration, with extracted block provenance; the successful run links a ready index and immutable [source snapshot](../source-history.md). Page visibility and provider revision behavior depend on the actual account, so validate them against your scoped test workspace before relying on a live refresh.

If no connection appears, use **Settings**. If a page is absent, share it with the integration and check the selected scope; an inaccessible page should not be represented as successfully indexed. After a failure or rate limit, inspect the item reason and safe retry status before rerunning. See [connections](../connections.md), [previews](../previews.md), and [runs](../runs.md). The capability boundary is the current adapter plus deterministic doubles, not a live workspace guarantee.
