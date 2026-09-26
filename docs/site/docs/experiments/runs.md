---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Run an experiment
slug: /experiments/runs/
---

Evaluate one saved answer pipeline version, or compare two on the same immutable dataset. First [import reviewed questions](./datasets.md), publish a ready index, and [save answer pipeline versions](../answers/pipelines.md). The server needs `EVALUATOR_MODEL`, a server-side model key and embeddings for **Response relevancy**. Query generation, evaluator calls and embeddings may be billed; the UI does not estimate dollars when pricing is unavailable.

1. Open **Experiments**. Under **Dataset version**, choose the reviewed version and inspect its questions. Under **Candidate configurations**, select **Candidate A** and optionally **Candidate B (optional)**. These must be distinct saved versions; test drafts are not candidates. Read each configuration's index and model before submitting.
2. Under **Metrics & execution**, enter **Experiment name** and select one or more **Evaluation metrics**: **Faithfulness**, **Response relevancy**, or **Context recall**. Review **Run summary** and the evaluator status. **Run experiment** is disabled if the evaluator is unconfigured or required inputs are missing.
3. Select **Run experiment** once. The returned run has its own URL and displays queued/running progress, completed item count and terminal status. **Cancel experiment** stops future calls; an in-flight call may finish. Use **All experiments → Experiment history** to reopen a run after reload.

Expected result: the run snapshots the dataset, saved candidate versions, index/source lineage, models, evaluator configuration and application source hash. Each question/candidate has an explicit output and metric state. A run with two candidates has two results per question; the total is not the number of questions alone. Failed/skipped results remain in the summary, and unknown cost stays unavailable. [Tutorial T4](./compare.md) follows two fictional versions through evidence and a paired comparison.

If submission fails, read the safe validation error before retrying; duplicate clicks can schedule separate paid work. If a job remains queued, check the worker and dispatcher via the [local install guide](../start/install.md). If cancelled or failed, inspect per-question status and only rerun after fixing the cause; the prior immutable record remains. The deterministic local journey verifies orchestration and display, not live RAGAS judgments or paid cost. See [metrics](./metrics.md), [comparison](./compare.md) and [current limits](../reference/limitations.md).
