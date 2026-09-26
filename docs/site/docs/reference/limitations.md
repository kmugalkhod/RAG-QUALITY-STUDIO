---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Current capability boundaries
slug: /reference/limitations/
---

Decide which instructions can be completed on the local stack and which need separate configuration or acceptance. Reviewed against current code and tests at commit `481b4eca90c5` plus this branch, 2026-09-26.

## Local deterministic path

You can start the [local services](../start/install.md), create a project, upload a supported synthetic document, process it, inspect chunks, save supported graphs and read `/openapi.json`. Isolated PostgreSQL/pgvector browser tests use deterministic provider doubles for indexing, answers and ingestion journeys. These tests establish application behavior under controlled responses, not provider accuracy or account access.

To check your own boundary, open **Settings** in a local project and read **Embeddings** and **Answer models**. Then open **Knowledge Base → Collections**. Expected result: upload and processing remain available; **Publish prepared documents** is enabled only when embeddings are configured. A disabled button or unavailable status is a configuration result, not a successful live-provider test. Do not retry publication until the server setting is corrected; see [provider configuration](../start/configure.md).

## Configuration and live gates

Publishing and answering require configured embedding/chat access and can incur charges. OCR capability depends on installed languages and settings. S3, Notion and Confluence need a configured encrypted connection and a permitted live account; Website ingestion must reach a bounded public HTTP(S) origin and observe its safety limits. OIDC/shared deployments require external key infrastructure and role validation, plus a separate live release gate. No such external account or shared deployment is verified by this local documentation review. See [security and permissions](../operate/security.md) and [limits and FAQ](./limits-faq.md).

## Unsupported guarantees and retry

The app does not guarantee that a model answer is factual, that a citation proves the whole answer, or that a similarity score is confidence. A preview does not publish an index. A failed/cancelled index is not ready. Arbitrary graph branching and code execution in nodes are outside the supported templates. When a feature is unavailable, inspect **Settings**, the relevant run state and [provider configuration](../start/configure.md); fix the cause, then make a new version/run where required. Read [the first workflow](../start/first-workflow.md) for a bounded local example, [API overview](../api/overview.md) for the current contract, and [troubleshooting](../operate/troubleshooting.md) for safe retries.
