---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Deploy the local workspace
slug: /operate/deploy/
---

Start the supported loopback workspace, identify its persistent stores, and decide what must be validated before any shared deployment. Run these commands from the repository root with Docker Compose v2, Node.js 22.12+, npm, and free ports 5432, 8000 and 5273. This page describes the current local Compose topology; it is not a shared-host deployment certification.

![The local API and worker share PostgreSQL and the document volume; Redis relays queued work and a dispatcher recovers it. External identity and key services are a separate shared-deployment gate.](/img/deploy-boundary.svg)

<a href="/img/deploy-boundary.svg">Open the service and storage diagram at full size</a>. In text: Vite reaches the loopback API; API, worker and dispatcher use PostgreSQL, Redis and persistent document storage; configured model calls leave the local boundary; OIDC and external key wrapping require a separate shared deployment.

## Start and check

1. Copy `.env.example` to `.env` only if no local `.env` exists. Choose a private URL-safe `POSTGRES_PASSWORD`. Keep provider and wrapping keys server-side, outside Git and `VITE_*`; a provider key is optional until you index, answer or evaluate.
2. Start **db**, **redis**, **migrate**, **backend**, **worker** and **dispatcher**. Do not start the Compose `frontend` service while Vite owns port 5273.
3. In a separate terminal, start the canonical Vite frontend. Check liveness and schema/database readiness before opening the app.

```sh
test -e .env || cp .env.example .env
# Edit .env before the first Compose start.
docker compose up --build -d db redis migrate backend worker dispatcher
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/ready
docker compose ps
cd frontend && npm ci && npm run dev -- --port 5273
```

Expected result: `/api/health` returns `{"status":"ok"}`, `/api/ready` returns `{"status":"ready"}`, and [the app](http://127.0.0.1:5273) opens. The one-shot **migrate** service exits successfully; **backend**, **worker** and **dispatcher** remain running. PostgreSQL, Redis and document artifacts use named `postgres_data`, `redis_data` and `document_data` volumes. Stop services with `docker compose down` when needed; it preserves these volumes. The local owner is restricted to loopback requests. A ready API does not establish model/provider availability; check **Settings → Models** before paid work.

## Shared-access gate

| Local behavior verified here | Additional shared-deployment requirement |
| --- | --- |
| Compose binds published ports to `127.0.0.1`; `AUTH_MODE=local` supplies one owner. | Configure `AUTH_MODE=oidc`, HTTPS JWKS, issuer, audience, TLS ingress and identity lifecycle. Test every project role against real tokens. |
| Local artifacts can use a separate 32-byte keyring. | Enable artifact encryption with `ARTIFACT_ENCRYPTION_MODE=kms` or `vault`, supply key references and test the external service. OIDC mode rejects disabled encryption or `local-keyring`. |
| Source-connection credentials are available only through the loopback vault when enabled. | Credentialed source routes still enforce a local Host/Origin/forwarded-header boundary; do not assume a public ingress exposes them. Design and validate an approved credential boundary before enabling remote connector management. |
| Local Vite and API share a workstation. | Supply ingress/TLS, CORS origin policy, secret injection, backup/restore, capacity and external provider budgets. This repository does not supply a verified shared ingress deployment. |

The `migrate` service runs `alembic upgrade head` before backend/workers start. For an upgrade, take a consistent [backup and restore point](./backup-restore.md), test the migrations on a restored copy, then roll backend, worker and dispatcher together. A changed parser or embedding model creates new immutable processing/index versions; do not rewrite a historical ready index. Model calls, OCR capacity and external source fetches have separate bounds and costs.

If health fails, inspect `docker compose ps` and `docker compose logs --since=30m backend migrate worker dispatcher`. If health works but readiness fails, inspect PostgreSQL and the migration exit status before retrying. If port 5273 is occupied, inspect and reuse/restart that Vite process; do not switch to another frontend port. If you changed the password after a database volume was initialized, the existing PostgreSQL role keeps its original password. Never remove named volumes to make startup appear successful. See [security and permissions](./security.md), [operations](./operations.md), [provider setup](../start/configure.md), and [current limits](../reference/limits-faq.md). This page was checked against the local manifests and isolated test stack; no external ingress, OIDC issuer, KMS/Vault or paid model was live-validated.
