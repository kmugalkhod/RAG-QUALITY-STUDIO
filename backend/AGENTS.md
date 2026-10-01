# Backend

## Overview

This area owns the API, persistent state, ingestion, answer execution, and evaluation. FastAPI accepts requests, PostgreSQL stores durable state, and Celery workers perform long running work. Read `../AGENTS.md` for product and security rules.

## Key files

`app/main.py` registers routers, middleware, and safe error responses. `app/api/` defines HTTP routes, while `app/services/` owns use cases. `app/schemas/` holds request and response contracts, and `app/models/` holds SQLAlchemy tables. `app/connectors/`, `app/ingestion_content/`, `app/pipelines/`, and `app/providers/` separate source access, content processing, RAG execution, and model access. `app/workers/` owns background tasks and the database queue dispatcher. `migrations/` owns schema changes.

`app/core/auth.py` resolves `AUTH_MODE` (`local`, `clerk` or `oidc`) into a principal and enforces project roles. `app/providers/openrouter.py` and `app/providers/generation.py` are the OpenRouter embedding and chat adapters; `app/pipelines/langchain_rag.py` compiles the validated answer graph into a LangChain runnable and records the runtime snapshot with each run. `app/core/connection_secrets.py` and `app/core/artifact_crypto.py` are the AES-GCM envelope boundaries for connection credentials and raw artifacts. `app/api/schedules.py` and `app/services/schedules.py` own ingestion schedules.

## Commands

From the repository root, you can run `docker compose exec backend python -m pytest`, `docker compose exec backend ruff check .`, and `docker compose exec backend ruff format --check .`. For database integration and migration checks, use the isolated stack in `compose.test.yaml` as described in `README.md`. The tests require an empty PostgreSQL database whose name ends in `_test`; without `TEST_DATABASE_URL`, database tests skip.

`scripts/check_experiment_live.py` is an opt-in three question check against a sample project on the running API. It spends provider credit and is not part of CI.

## Conventions

Keep routes thin and put database transactions and provider calls in services, workers, or adapters. Apply persisted schema changes through Alembic. Keep project and organization scope in every data access path. Preserve immutable pipeline, source, index, and experiment versions. Use database backed checkpoints and fenced execution tokens for work that may be delivered again. Keep secrets, raw artifacts, and unsafe provider errors out of API responses and logs.

Connectors in `app/connectors/` (existing files, website, S3, Notion, Confluence) implement the contracts in `base.py`. Credentialed kinds return unavailable unless `SOURCE_CONNECTIONS_ENABLED` and an active connection key are configured; `safe_http.py` is the SSRF boundary for website fetches.

## Gotchas

`app/db/session.py` uses repeatable read for ordinary sessions and read committed for deployment admission. The deployed answer and widget paths share one durable run and worker flow; do not create a separate browser answer executor. Private widget exchange uses a server held deployment key; opt-in public mode uses a Studio-issued visitor token. Browser routes require a short lived widget token and exact frame origin in both modes. The widget code is current local work; check Git status before editing it.

## Related documents

See `../docs/architecture.md`, `../docs/implementation-plan.md`, `../docs/development.md`, and `../docs/website-chatbot-widget-plan.md` for the active contracts and verification record.

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
