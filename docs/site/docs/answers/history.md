---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: Reopen past questions
slug: /answers/history/
---

Reopen a persisted answer query and inspect the exact evidence and configuration used at the time. You need a project with at least one completed **Pipeline test**; [the first workflow](../start/first-workflow.md) creates one. Retrieval-only tests do not appear in this history.

1. Open **Playground → Pipeline test → Past questions**. Select **Refresh** if a newly completed question is absent, then use **Previous queries** or **Next queries** to page through results.
2. Select a question. Read its label: **Pipeline v[number]**, **Test draft**, or **Default settings**, followed by status. Open **Sources & details** to inspect the recorded index version, retrieved passages, usage and cost basis. A later index or pipeline change does not rewrite this query record.
3. Compare the selected result with another run only after checking that they used the same index and saved version. Query latency covers query execution, not indexing, queue wait or evaluation.

Expected result: the selected answer and its evidence can be reopened after a page reload. A failed or insufficient-evidence run remains visible rather than being silently counted as a good answer. A query created just before an interruption may be marked failed by stale-run recovery; submit a new question after correcting the underlying problem. Query execution is currently non-streaming and has no cancellation control. An unknown provider price is shown as unavailable, not free.

If history is empty, confirm you are in the same project and have run **Pipeline test** rather than **Retrieval test**. If a selected run cannot load, use **Refresh**, check project access, and read the API error before resubmitting. This page covers local persisted query behavior; live model accuracy and shared access are separate gates. See [Playground modes](./playground.md), [evidence](./evidence.md), and [version provenance](../concepts/versions.md).
