---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Knowledge Base
slug: /knowledge-base/
---

Find the two local content workspaces and the artifact each creates. UI labels verified against commit `481b4eca90c5` plus copy updates, 2026-09-26.

## Prerequisite

Open a project in the [local app](../start/install.md). Upload and preparation can run without model credentials; publishing and retrieval need [configured embeddings](../start/configure.md), which may be billed.

## Navigate

1. Select **Knowledge Base** in project navigation. **Documents** shows uploaded files and their processing history. Select **Add document** to upload one file.
2. Select **Collections**. Within this view, **Collections** lists searchable versioned indexes and **Source history** lists reusable source snapshots from supported remote ingestion runs. A new local upload does not immediately appear as a ready collection.
3. Prepare a file with **Start processing**. Then choose **Publish prepared documents** from Collections. Open the resulting collection and inspect **Overview**, **Sources**, **Versions**, **Passages**, and **Test retrieval**.

Expected result: a prepared document appears under Documents; a successful embedding/publication becomes a **Ready** collection version. If Collections is empty, check whether processing succeeded. If publishing is disabled, inspect **Settings → Embeddings**. If a version failed, refresh its status before retrying. Continue with [documents](./documents.md), [preparation](./prepare.md), and [collections](./collections.md). Remote Source history needs a configured source; no external account is implied by the visible tab.
