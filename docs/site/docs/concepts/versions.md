---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Versions and provenance
slug: /concepts/versions/
---

Identify the exact content and settings behind a result. Applies to the current local application at commit `481b4eca90c5`, reviewed 2026-09-26; legacy records may have less lineage.

## Prerequisite and inspection

Complete the [first workflow](../start/first-workflow.md), including one ready collection and a saved answer version. Open **Knowledge Base → Collections**, select **Uploaded documents**, then inspect **Sources**, **Versions**, and **Passages**. The collection is the named group (API `knowledge_set`); each index version is an immutable searchable membership. **Current** points to the latest successfully published version. A historical ready version remains selectable by its ID.

Open **Pipelines → Answer pipelines** to inspect the saved graph version. In **Playground**, **Pipeline test** shows which saved version is used; **Sources & details** shows retrieved evidence for an answer. A draft test may not be the saved version, so check the toolbar and answer details before comparing results. Ingestion source snapshots, when available, record an external collection revision separately from any downstream index.

Expected result: you can state the document/processing version, ready index version and answer-pipeline version for your run. If a referenced version is unavailable, refresh its list and inspect the run or deletion state; never replace its ID with a current version silently. Retrying an operation creates new run/version history and may incur provider cost. See [collections](../knowledge-base/collections.md) and [API patterns](../api/patterns.md). Remote snapshot reuse and live connector provenance require separate source configuration and are outside this first local workflow.
