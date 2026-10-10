---
verified_against: "481b4eca90c5 + docs phase 2 working tree (2026-09-26)"
title: Chunking and embedding
slug: /ingestion/chunking/
---

Choose passage boundaries, inspect exactly what will be embedded, and publish a version compatible with the selected embedding model. Schema-v2 supports three chunking algorithms; changing one creates a new index variant rather than rewriting an old ready version.

## Prerequisites

Use a [saved source and extraction draft](./pipelines.md), configured embeddings, and a source you may process. Indexing makes at least one embedding request for included chunks and may be billed; the app reports known counts, while dollar cost is unknown without provider pricing. The backend supplies the Embed node's provider, model, dimensions and configuration version; mismatched dimensions cannot be mixed into a destination index.

## Compare passage shapes

1. Select **Chunk** in the stage navigation. Under **Chunking algorithm**, choose **Section-aware tokens**, **Parent and child**, or **Character window (compatibility)**. Token limits use the app's stable UTF-8 byte tokenizer, not a promise of the answer model's exact token count.
2. For **Section-aware tokens**, set **Target tokens**, **Hard maximum tokens** and **Overlap tokens**. For **Parent and child**, set child and parent targets/maxima and child overlap; child chunks are embedded and retrieval supplies saved parent text as evidence. For **Character window**, use a preset or **Chunk size (characters)** and **Overlap (characters)**. Overlap must remain smaller than the target/size. **Add heading context to embedding text only** does not change the evidence text.
3. Select **Preview processing → Inspect stages → Chunks**. Read the count, boundaries, evidence text and any embedding prefix. Save a version and run only after the boundaries make sense. Open **Inspect published index** to verify membership and model metadata.

New pipelines use `section-token-v2` and `parent-child-v2`. When a section on a page starts with a piece under 40 tokens, such as a chart label or callout that extraction read as a heading, v2 appends it to the passage before it on the same page, provided the result stays within the hard maximum, so it is not left as a passage of a few words that search rarely ranks first. In **Parent and child** the rule applies to parents and, inside each parent, to children. The merged passage keeps the section heading of the passage it joins. A version saved with `section-token-v1` or `parent-child-v1` keeps its chunking so earlier runs reproduce; its Chunk settings show **Saved with …** and an **Upgrade chunking** button, and saving the upgrade creates a new pipeline version whose next run chunks and embeds documents again.

Expected result: the preview describes passage shape without embedding; the run embeds included chunks and publishes a new ready index only on success. A second version using the same [source snapshot](./source-history.md) can have a different count without another network collection, but embedding work may recur.

If validation rejects a target, hard maximum, overlap or destination dimension, correct the labeled field and preview again. If an item yields no useful passage or an oversize finding, inspect **Extracted** and **Cleaned** before increasing limits. A failed/cancelled index remains non-ready; keep the previous ready version. See [quality](./quality.md), [source history](./source-history.md), and [collection versions](../knowledge-base/collections.md). Local deterministic tests cover the algorithms and compatibility; provider quality and charges require the reader's configured account.
