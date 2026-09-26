---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Confluence source
slug: /ingestion/sources/confluence/
---

Collect only accessible Confluence pages within a bounded scope and inspect revisions before publication. The connector and failures are covered by deterministic tests; a real Confluence site/account remains a separate live acceptance gate.

## Prerequisites

Save a scoped Confluence **Site URL**, **Account email**, and **API token** through the local encrypted [source vault](../connections.md). Test the connection with an account that can read a small test space or page. Configure embeddings for publication. Credentials remain in the server vault; source settings store the connection ID. Provider/API and model charges may apply, with dollar cost dependent on your account.

1. In **Pipelines → Ingestion pipelines → New ingestion pipeline**, select the Source node and choose **Confluence** under **Source type**. Choose **Confluence connection**.
2. Under **Discovery scope**, choose **All accessible current pages**, **Explicit space IDs**, or **Explicit page IDs**. Explicit IDs are numeric provider IDs, one per line. Optionally constrain **Included title prefixes**, **Excluded title prefixes** and **Required label IDs**.
3. Set **Maximum pages**, **Maximum API requests**, bytes per API response, text characters per page and timeout. Select **Preview processing** and inspect location, revision, status and reason. Save with **Save version**, then select **Run ingestion**.

Expected result: a successful run produces a ready index whose members come from the saved page revisions, with a linked [source snapshot](../source-history.md). A page hidden from this account is not included merely because its URL exists. Test this scope and revision behavior with your own account before relying on a live refresh.

If **No Confluence connection is available**, use **Settings**. On permission loss, malformed IDs or failed extraction, read the preview/run reason, correct access or selection, save a new version when settings change, and retry after checking the prior run's terminal status. See [previews](../previews.md), [runs](../runs.md), and [quality findings](../quality.md). This page applies to the current schema-v2 adapter and does not claim external account validation.
