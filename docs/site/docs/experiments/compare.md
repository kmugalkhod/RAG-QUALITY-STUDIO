---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Compare two answer pipelines
slug: /experiments/compare/
---

Compare two saved answer versions on the same reviewed questions and inspect every result behind the aggregate. This is tutorial **T4**. It is verified on an isolated PostgreSQL/pgvector stack with deterministic provider doubles. Real answer/evaluator calls require separate configuration and may incur cost; the fixture's scores are not evidence that either pipeline is better.

![The same ready index feeds two saved answer versions and two reviewed questions; four item outcomes remain visible while paired differences use only shared successful scores](/img/paired-comparison.svg)

<a href="/img/paired-comparison.svg">Open the comparison diagram at full size</a>. In text: both candidates receive the same questions and index; each candidate-question pair is persisted, while a metric difference uses only pairs scored for both.

## T4: one corpus, two candidates

1. In a new isolated project, upload <a href="/examples/orchard.txt">orchard.txt</a> under **Knowledge Base → Documents → Add document**. Select **Start processing**, inspect its chunks, then under **Collections** select **Publish prepared documents** and wait for a ready version. This uses the same UI sequence as the [first workflow](../start/first-workflow.md). The source is fictional and contains no launch code.
2. Open that collection and select **Use version [number] in a pipeline**. Name the answer pipeline `Orchard comparison`, choose **Selected node → Retriever**, set **Top k** to `1`, and select **Save version**. Choose **Selected node → Retriever** again, change only **Top k** to `2`, then select **Save version**. Check that versions 1 and 2 use the same ready index and model. Changing only retrieval settings does not rebuild the index.
3. In **Experiments → Dataset → Import a reviewed CSV**, import <a href="/examples/orchard-reviewed.csv">orchard-reviewed.csv</a> as `Reviewed orchard`. **Preview CSV** must show two questions: one with an apple reference and one without a launch-code reference. Select **Import reviewed dataset**, then select that **Dataset version**.

   ![Reviewed fictional dataset preview with one answerable apple question and one launch-code question without a reference](/img/screenshots/13-reviewed-dataset.png)

   <a href="/img/screenshots/13-reviewed-dataset.png">Open the dataset preview at full size</a>.

4. Under **Candidate configurations**, choose `Orchard comparison · v1` as **Candidate A** and `Orchard comparison · v2` as **Candidate B (optional)**. Under **Metrics & execution**, enter a name, select **Faithfulness**, **Response relevancy** and **Context recall**, read **Run summary**, then select **Run experiment**. The local deterministic journey completes four question/candidate results. A configured live run can vary and bill for generation and evaluation.
5. After terminal status, read **Candidate summaries** before **Paired comparison**. Compare scored/total and unavailable counts. Open each question under **Per-question comparison** and inspect the answer, cited passage and metric reason for both candidates. The launch-code row should be treated as an abstention, and its missing reference makes context recall unavailable. Select **Export CSV** to retain row statuses and lineage, then reopen the run through **All experiments → Experiment history**.

   ![Two fictional candidates have one scored and one unavailable value per selected metric, with unknown monetary cost](/img/screenshots/14-candidate-summary.png)

   <a href="/img/screenshots/14-candidate-summary.png">Open candidate summaries at full size</a>.

   ![Paired comparison uses one shared scored question and shows zero difference under the deterministic judge](/img/screenshots/15-paired-comparison.png)

   <a href="/img/screenshots/15-paired-comparison.png">Open the paired comparison at full size</a>.

   ![Per-question table keeps the answerable result and the insufficient-evidence result visible for both candidates](/img/screenshots/16-question-comparison.png)

   <a href="/img/screenshots/16-question-comparison.png">Open the per-question comparison at full size</a>.

Expected result in the deterministic journey: both candidates use the same dataset and index, and the interface preserves all four item outcomes. The fixed test judge returns equal successful values, so paired differences are zero where both scores exist. The unanswerable row reduces the shared scored sample. That is a test of comparison bookkeeping, not a recommendation. The summary warns when candidates use different source snapshots or legacy lineage; the Orchard upload has no remote snapshot, so check the identical index IDs in **Immutable run configuration** rather than treating the warning as a content change.

If a candidate is absent, save that answer pipeline version and refresh **Experiments**. If **Run experiment** is disabled, read the evaluator error and confirm the dataset and metrics. If a row fails, inspect **Question evidence** and the safe error; do not drop it to improve the mean. A cancelled run may contain completed and skipped rows. If **Export CSV** is unavailable or returns an error, reopen the terminal run and retry only the download. Continue with [metric requirements](./metrics.md), [interpreting differences](./interpret.md) and [version provenance](../concepts/versions.md). Live paid calls and external accounts have not been verified for this tutorial.
