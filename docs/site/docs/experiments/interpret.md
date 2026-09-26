---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Interpret and improve results
slug: /experiments/interpret/
---

Choose a bounded next change from per-question evidence, then rerun it against the same reviewed dataset. You need a completed [paired comparison](./compare.md) with saved candidate/index identities and visible failure counts. The app reports measured outputs; it does not prove a root cause or certify accuracy.

| What you observe under **Per-question comparison** | Check before changing a version | Possible next experiment |
| --- | --- | --- |
| Relevant passage absent from both candidates | Ready index membership, chunk boundaries, query method and **Top k** | Change one retrieval setting or prepare a new index, and record that the corpus changed if you rebuild it. |
| Relevant passage present, answer unsupported | Exact supplied passage, prompt and model settings | Save a new answer pipeline version with one prompt/model change. Do not call faithfulness factual accuracy. |
| Answer abstains | Whether the source truly contains the answer | Keep the abstention if evidence is absent; otherwise test retrieval before loosening generation behavior. |
| A metric is unavailable or failed | Its per-question reason and required inputs | Add a reviewed reference only in a new dataset version, or repair evaluator configuration; never invent a score. |
| Small aggregate difference | Shared paired sample, failed/skipped counts, index/source lineage and model variability | Repeat on a held-out set before recommending a configuration. |

For a concrete local exercise, start from T4, change only **Top k** in the answer editor, select **Save version**, and rerun **Experiments** with the same **Dataset version** and selected metrics. Compare the new **Paired comparison** and each **Question evidence** view. If you changed source documents, chunking or embeddings, call it a different corpus and interpret the result separately. Keep a held-out dataset when tuning repeatedly; the UI does not enforce one.

Expected result: a new immutable run and candidate version with inspectable lineage, not an automatic best-pipeline claim. If the sample is too small, costs unknown or failures nonzero, state that limit alongside any observed difference. A deterministic provider double can verify the workflow and counts, but cannot validate real relevance or judge reliability. For a failed rerun, inspect the run status and item reasons before another potentially paid attempt. See [metrics and costs](./metrics.md), [retrieval settings](../answers/retrieval.md), and [source history](../ingestion/source-history.md).
