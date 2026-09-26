---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Troubleshoot a blocked workflow
slug: /operate/troubleshooting/
---

Identify the saved state and safe next action before retrying a workflow that may spend provider money. You need the exact project, run/index ID and safe application error, plus access to **Settings**, the relevant run inspector or loopback API. Start with `curl --fail http://127.0.0.1:8000/api/health` and `/api/ready`; a live API and a ready database are separate checks.

![The project Settings model panel shows unavailable embeddings and answer models when the server has no provider key; the provider setup link leads to the server-side configuration guide.](/img/screenshots/17-provider-unavailable.png)

<a href="/img/screenshots/17-provider-unavailable.png">Open the sanitized provider-unavailable Settings view at full size</a>. The image uses a fictional isolated project; the instructions below remain usable without it.

![At 390 pixels wide, the same Settings model panel keeps the unavailable embedding reason and answer-model configuration hint readable.](/img/screenshots/18-provider-unavailable-mobile.png)

<a href="/img/screenshots/18-provider-unavailable-mobile.png">Open the mobile Settings view at full size</a>.

| Symptom | Inspect | Safe action and expected result |
| --- | --- | --- |
| **Settings → Models** shows embeddings unavailable, or **Publish prepared documents** is disabled | Server-side `OPENROUTER_API_KEY`, supported embedding model/base URL/dimensions; do not inspect the key value in logs. | Configure the server and restart backend and worker, then refresh **Settings**. The status becomes configured; indexing may incur charges. Upload/preparation can still work without embeddings. |
| **Answer models** or **Run pipeline test** is unavailable | `CHAT_MODEL`, allowed `CHAT_MODELS`, server key, ready index and saved/draft graph validation. | Correct the server model and selected index, refresh, then run one bounded query. An unavailable dollar price remains unknown. |
| 422 on upload, graph, preview or schedule | Validation `detail`, field bounds and installed `ingestion-capabilities`. | Correct the exact field/file and preview again; never bypass server validation. Unsupported macro/encrypted Office files and unreadable PDFs fail safely. |
| 409 after a write or 410 on raw content | Active/terminal job, preview content hash, ready-index compatibility, or raw-artifact retention state. | Refresh/list the saved resource before resubmitting. For 410, use a retained revision if available; current remote bytes are a different revision. Do not delete history to clear the error. |
| OCR language or scanned PDF fails | **Extract → OCR languages**, server capabilities, page findings and scan quality. | Install the language pack in every worker image, choose bounded OCR policy and make a new preview/version. OCR output still needs review. |
| Website target is blocked | Public DNS and every redirect, allowed origin, page/size/time/depth limits. | Choose a permitted public HTTP(S) source. Private, loopback and metadata-service addresses are intentionally blocked; do not add a proxy to evade the check. |
| S3/Notion/Confluence connection fails | **Settings → Source connections → Test connection**, safe status, account scope and key version. | Rotate only a scoped credential and test again. Local vault must be enabled; an external account has not been validated by the docs fixture. Avoid repeated paid ingestion as a credential probe. |
| Job remains queued/running or a new index is absent | Run progress, worker/Redis/dispatcher status, stale age and terminal item reasons. | Restore the failed service and let fenced recovery run; a failed/cancelled index cannot become ready. Create a new run only after understanding the old result. |
| Experiment metric is unavailable or cost blank | **Per-question comparison** reason, reference answer, evaluator/embedding configuration and pricing basis. | Add a reviewed reference in a new dataset version or correct the evaluator. Preserve unavailable/failed/skipped rows; unknown price is not zero. |
| 401, 403, 404 or 503 on protected reads | Authentication token, project role, resource ID, migration/key-service state. | Fix the corresponding access or service boundary. Do not expose tokens or source text while debugging; see [security](./security.md). |

Expected result: you can identify whether a failure is configuration, input validation, access, source availability, worker delivery or evaluator input, then retry only the affected new operation. A timed-out POST may already have persisted a resource; list/refresh before sending another paid request. For details, use [local deployment](./deploy.md), [operations](./operations.md), [provider setup](../start/configure.md), [ingestion quality](../ingestion/quality.md), and [metrics](../experiments/metrics.md). The missing-provider state was reproduced on an isolated local stack; live account, model, key-service and shared ingress failures require authorized checks in their own environment.
