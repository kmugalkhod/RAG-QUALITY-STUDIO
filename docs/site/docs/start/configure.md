---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Configure model providers
slug: /start/configure/
---

Enable embedding and answer actions and check what the running server reports. Applies to the current local app at commit `481b4eca90c5`, reviewed 2026-09-26. Provider availability and billing depend on your account.

## Prerequisites and costs

Start the [local stack](./install.md). You need an OpenRouter account and key for the currently supported embedding and chat adapters. Index publication makes embedding requests; a pipeline test makes embedding and generation requests. Experiments can make additional generation and evaluator requests. These calls are potentially paid; deterministic test providers are confined to isolated tests.

## Configure

1. Edit only the root `.env` on your machine. Set `OPENROUTER_API_KEY`, `EMBEDDING_PROVIDER=openrouter`, a supported `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, and `CHAT_MODEL`. Keep model name and dimensions compatible. Set `EVALUATOR_MODEL` only if you intend to run experiments.
2. Recreate the API, worker and dispatcher so their environment changes take effect: `docker compose up --build -d backend worker dispatcher` from the repository root.
3. In a project, open **Settings**. Check **Embeddings**, **Embedding model**, and **Answer models**. Settings shows safe status and model identifiers, never keys.
4. Open **Knowledge Base → Collections**. **Publish prepared documents** is disabled when embeddings are unavailable. Open **Playground** and check model availability before asking a question.

```sh
curl --fail http://127.0.0.1:8000/api/ready
docker compose logs backend worker dispatcher
```

Readiness proves database/schema access, not paid-provider reachability. If Settings reports an unavailable embedding or answer model, correct the server setting, recreate services, and refresh the page. If a provider call fails after a job starts, inspect the run status before retrying to avoid duplicate paid work. An index must reach **Ready** before retrieval. Continue with the [first workflow](./first-workflow.md) or [current limitations](../reference/limitations.md). No live provider account was used to verify these instructions.
