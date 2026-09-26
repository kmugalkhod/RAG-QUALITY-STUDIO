---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: Install locally
slug: /start/install/
---

Start a loopback-only workspace and confirm the API and database schema are healthy. These commands match the current Compose and Vite manifests, reviewed 2026-09-26 at app commit `481b4eca90c5`.

## Prerequisites

Docker Engine/Desktop with Compose v2, Node.js 22.12+, npm, and free local ports 5432, 8000 and 5273. Run commands from the repository root. The database, Redis and artifacts use persistent volumes. The default local mode is one loopback owner; it is not a verified shared deployment.

## Start services

1. Copy the configuration template and set a private, URL-safe database password in `.env`. Do not commit this file.
2. Start the database, migrations, API and workers.
3. Start Vite in a separate terminal at the canonical app URL.

```sh
test -e .env || cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and any provider settings you intend to use.
docker compose up --build -d db redis migrate backend worker dispatcher
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/ready
cd frontend
npm ci
npm run dev -- --port 5273
```

Open [the local app](http://127.0.0.1:5273). `/api/health` should return `{"status":"ok"}`; `/api/ready` should return `{"status":"ready"}` after migrations. The Vite terminal must remain running. Do not run the Compose `frontend` service at the same time.

## If startup fails

Run `docker compose ps` and `docker compose logs backend migrate worker dispatcher`. A ready failure indicates the database or migration is unavailable; a healthy API alone does not prove database readiness. A port conflict means another process already owns that port: inspect it and reuse or stop that process before retrying. If a database volume already exists, changing the password in `.env` does not change that database role's password. `docker compose down` stops services while retaining named data volumes; never use `down -v` for routine cleanup.

Next, [configure providers](./configure.md) for indexing and answers, or [upload a document](../knowledge-base/documents.md) without model calls. The local commands were checked against manifests; a fresh installation on every supported host has not been live validated.
