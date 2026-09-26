---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Retrieval settings
slug: /answers/retrieval/
---

Choose how a ready index returns passages, then inspect the actual ranks and scores before changing an answer pipeline. You need a ready index in the current project; [publish the fictional Harbor file](../start/first-workflow.md) or use your own authorized source. Vector and hybrid search may call the configured embedding provider and incur cost. Keyword search does not embed the query.

## Compare search methods

1. Open **Playground → Retrieval test → Retrieval settings**. Under **Documents to search**, select a ready collection version. Enter a **Search query** and select **Run retrieval test**. This returns passages only; it does not call the answer model or create a saved question run.
2. In **Search settings**, select **Search method → Vector** and set **Top k** from 1 to 50. **Advanced search settings → Maximum vector distance (optional)** accepts 0–2 or a blank value for no cutoff. A smaller cosine distance is closer in vector space, not a probability of correctness.
3. Repeat with **Keyword**. This uses prepared chunk text and needs no query embedding. Then try **Hybrid**: **Vector candidate count** and **Keyword candidate count** must each be at least **Top k** and at most 200. **Vector weight** is 0–1; the other branch receives the remaining weight. A zero-weight branch is skipped. The distance cutoff applies only to the vector branch.
4. Open a result with **View passage [rank]**. Read the exact evidence text and **Source details**. **Settings used for this search** shows the normalized settings and diagnostics. Compare the same query and index across methods; record whether a useful passage was returned, not just its numerical score.

Expected result: a ranked list of at most Top k passages with the exact index version, method-specific score fields and a score-semantics note. Hybrid uses reciprocal rank fusion (RRF); keyword and fusion scores rank results within their methods. They are not confidence values or directly interchangeable with cosine distance. The current editor has no reranker. A saved answer pipeline stores the selected retrieval settings in its version; changing them in a Playground test does not rewrite that version.

If there are no matches, confirm the index is **Ready**, inspect its membership and chunks, then try a broader query or remove an overly strict vector cutoff. If the selected index is incompatible with the configured embedding model, use a compatible ready version rather than mixing dimensions. If a setting fails validation, correct the field range shown beside it and rerun. The schema-v2 method bounds and local PostgreSQL retrieval paths are tested; quality on a particular corpus and paid provider behavior require their own check. Continue with [Playground modes](./playground.md), [evidence inspection](./evidence.md) and [collections](../knowledge-base/collections.md).
