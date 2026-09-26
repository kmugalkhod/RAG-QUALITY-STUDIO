---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Source connections
slug: /ingestion/connections/
---

Save a project-scoped connection reference, test its access, and rotate it without exposing the credential in a pipeline version. This guide describes the current **local encrypted connection vault**; a real S3, Notion, or Confluence test needs an account you control and has **not** been accepted against a live account for these docs.

## Prerequisites and boundary

Open a local project as an owner with **Settings** access. The server must explicitly enable source connections and have a versioned 32-byte connection key; [provider configuration](../start/configure.md) explains where server settings belong. The API restricts this vault to loopback requests and rejects forwarded requests. A public/shared deployment needs its own approved credential and key boundary; local vault coverage does not establish that gate. Have a scoped read credential for exactly one test source before selecting **Test connection**. Never put it in a pipeline node, URL, screenshot, or docs example.

## Save and check

1. In **Settings → Source connections**, select **Add connection**. Give it a **Connection name**, choose **Provider** (`Amazon S3`, `Notion`, or `Confluence`), and enter that provider's credential fields. Select **Save encrypted connection**.
2. Select the saved connection. Expect only its name, provider, redacted summary and status. Select **Test connection** to check the account's current access. A saved connection can be `untested` until checked; saving alone does not prove permission to a bucket, page, or space.
3. To replace access, select **Rotate credentials**, enter every credential field again, then select **Rotate credentials** in the form. Test it again. **Re-encrypt with active key** rewraps the saved secret under the configured active key; it does not validate provider access.
4. In **Pipelines → Ingestion pipelines**, select the Source node and choose the same provider under **Source type**. Select the connection by name in its provider-specific field. Only an opaque connection ID is saved in the version.

Expected result: the connection appears with safe metadata, a successful live test reports valid access, and the source selector offers it. The isolated browser suite checks redaction, rotation and rewrap with deterministic provider doubles; it does not certify an external account.

If **Encrypted connections are disabled** appears, configure the server key and local vault before retrying. If a test fails, inspect the safe error, verify the source account's read permission and scope, rotate when needed, and test again before previewing. Do not repeatedly run ingestion to diagnose bad credentials: fetched content and embeddings can have separate costs. Continue with [choosing a source](./sources/index.md), [S3](./sources/s3.md), [Notion](./sources/notion.md), or [Confluence](./sources/confluence.md). This page applies to schema-v2 ingestion at the verified commit above; shared credential deployment is outside this local release boundary.
