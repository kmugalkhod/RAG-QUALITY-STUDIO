---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Source history and snapshot reuse
slug: /ingestion/source-history/
---

Build a second index from the exact captured remote source revisions without collecting them again. This is tutorial **T3**. Snapshot reuse is locally tested with a deterministic Website transport; without an approved public fixture host or a separately configured account, the reader-facing remote collection step is conditional.

## Prerequisites and cost

Use an isolated project, configured embeddings, retained encrypted raw artifacts and one permitted remote source. A bounded public Website you own is the simplest option; follow [Website source](./sources/website.md). The controlled `controlled.example` host in browser tests is test transport only, not a live tutorial URL. A real first collection can contact a website or account and incur provider/API usage. The variant does not refetch that source, but it can reprocess and re-embed every included item; model cost may recur and dollar cost is unknown until provider pricing is known.

![Remote collection fixes source revisions in Snapshot 1; two saved pipeline versions produce separate ready indexes from that same snapshot](/img/source-lineage.svg)

<a href="/img/source-lineage.svg">Open the lineage diagram at full size</a>. In text: one remote collection creates a fixed snapshot; pipeline versions 1 and 2 each build a separate index from it; a future refresh creates a different snapshot.

## T3: collect, then reuse

1. In **Pipelines → Ingestion pipelines**, configure the Source node for a small public Website scope, bound **Maximum pages** and rate, and inspect **Preview processing**. Select **Save version**, then **Collect source & publish index**. Wait for success and follow **Inspect source snapshot**. This first run creates a ready snapshot only after the required remote items succeed.
2. In **Knowledge Base → Collections → Source history**, select that **Snapshot [number]**. Read **Included items**, **Changed / new**, **Failed**, **Captured items**, and **Derived indexes**. Record the snapshot ID from its current app URL or project-scoped API read; the displayed number alone is not a globally unique ID.

   ![Ready synthetic source snapshot with included item counts and one derived ready index](/img/screenshots/11-source-snapshot.png)

   <a href="/img/screenshots/11-source-snapshot.png">Open the source snapshot capture at full size</a>.

   The controlled `controlled.example` origin in this capture is supplied by test-only transport; it is not a public host for readers.

3. Return to the saved ingestion pipeline. Change the **Chunking algorithm** or its target/overlap in **Stage settings → Chunk**, then select **Save version**. This creates a distinct immutable pipeline version. Do not edit the original run or snapshot.
4. Return to the same snapshot. Under **Create an index variant from this snapshot**, choose the new **Ingestion pipeline version**, choose **New index**, enter a distinct **Index name**, and select **Create index variant**. Wait for `Run succeeded` and refresh the snapshot if needed.
5. Under **Derived indexes**, open both ready versions. Compare their pipeline version, chunk count and source membership. Both should link back to the same snapshot; their passages may differ. The editor also offers **Ready source snapshot → Reprocess saved source** for a saved Website version.

   ![Same synthetic snapshot after a second ready index variant was built with ingestion pipeline version two](/img/screenshots/12-snapshot-variant.png)

   <a href="/img/screenshots/12-snapshot-variant.png">Open the index variant capture at full size</a>.

Expected result in the deterministic browser journey: the variant uses the stored snapshot ID and cached artifacts, makes no second Website request, and leaves the first ready index available. The API run records `source_input.kind=snapshot` and the new destination. Remote source refresh is a separate action; **Refresh source** on the snapshot starts a new collection from the prior lineage rather than rewriting this snapshot.

If the snapshot is absent, confirm that the first run reached terminal success and select **Source history** again. If no compatible version appears, save a remote pipeline version for the same source kind. The server also checks exact source identity, retained artifacts, access and embedding compatibility; a matching dropdown kind alone is not approval. If an artifact expired or its key is unavailable, do not silently refetch and call it the same snapshot—restore authorized access or collect a new snapshot/version. If the variant fails, inspect its run and item reasons before retrying. Continue with [version provenance](../concepts/versions.md), [chunking](./chunking.md), and [run inspection](./runs.md). Live remote accounts, public fixture hosting and paid embeddings have not been verified for this guide.
