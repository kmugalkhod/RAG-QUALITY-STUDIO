---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Understand metrics and costs
slug: /experiments/metrics/
---

Read what each score requires before interpreting a comparison. Open a completed run from **Experiments → Experiment history**, then read **Candidate summaries**, **Paired comparison** and the metric details under **Per-question comparison**. You need an existing run; [T4](./compare.md) creates a deterministic example.

| Measurement | Inputs and meaning | Unavailable or caution |
| --- | --- | --- |
| **Faithfulness** | Answer and retrieved passages supplied to the model. Estimates whether the answer is supported by that context. | Empty context or abstention makes it unavailable. Support in supplied context is not overall factual accuracy. |
| **Response relevancy** | Question, substantive answer and configured embeddings, judged with generated questions. | Abstention/empty answer or missing evaluator embedding configuration prevents a score. Its cosine-based result can be negative; do not clamp it to a 0–1 confidence claim. |
| **Context recall** | Question, supplied passages and a human-reviewed `reference_answer`. | Missing reference is `unavailable: missing_reference`; an empty context is unavailable. A blank reference must never receive an invented zero. |

The application uses a versioned RAGAS adapter and records evaluator model, prompts, parameters, RAGAS version and implementation hash in the immutable run snapshot. Model-judged results can vary, including for unchanged inputs. Inspect the saved per-question reason and evaluator details before assuming a small difference is meaningful.

**Candidate summaries** show a mean of successful values only, plus scored/total, failed, skipped, unavailable and pending counts. **Paired comparison** includes only questions scored for both candidates on that metric; its **Shared sample** can be smaller than either candidate's scored count. **B − A** is the paired mean difference, not proof that a single setting caused the change. A deterministic test judge returns fixed values to verify the UI path; its numbers are not a measured quality result.

Expected result: you can identify which questions contributed to each mean, which did not, and why. In the reviewed Orchard example, the question without a reference has unavailable context recall rather than an invented zero; the paired sample excludes that question for this metric.

Query latency is query execution time, separate from indexing, queue wait and evaluation. **Generation cost** and **Evaluation cost** are separate known sums with known/total counts; an unavailable price is not zero. Indexing costs are outside these run totals. Read **Per-question comparison → [question] → Candidate A/B** for the answer, cited evidence, metric state, token usage and cost basis. If a score failed or is unavailable, read its reason and correct the missing input or evaluator configuration before another paid run. This page reflects the current local evaluator contract; live provider accuracy, pricing and variability require authorized checks. See [run experiments](./runs.md), [interpret results](./interpret.md) and [API patterns](../api/patterns.md).
