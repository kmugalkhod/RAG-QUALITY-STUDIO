---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Operate jobs and storage
slug: /operate/operations/
---

Find a stalled job, check capacity and restart safe delivery without changing saved results by hand. You need a running local Compose stack and operator access to its logs; use a selected project ID only for project-scoped API reads. Worker and dispatcher processes are separate from FastAPI, and PostgreSQL holds the authoritative job state.

![Jobs move from queued to running and then succeeded, failed or cancelled; the dispatcher can reclaim stale running work with a fenced token, while a partial index never becomes ready.](/img/job-states.svg)

<a href="/img/job-states.svg">Open the job-state diagram at full size</a>. In text: API writes a queued row, dispatcher relays it through Redis, worker checkpoints progress, and terminal rows retain success, failure or cancellation; stale recovery uses a new fence and retry budget.

## Check health and a saved run

Run from the repository root. The API's liveness check does not prove PostgreSQL readiness; use both endpoints and inspect the durable run in **Knowledge Base → Collections**, **Ingestion run progress**, **Past questions** or **Experiments → Experiment history** as appropriate.

```sh
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/ready
docker compose ps
docker compose exec worker celery -A app.workers.celery_app:celery inspect ping
docker compose logs --since=30m backend worker dispatcher
```

Expected result: health and ready both report their status, the worker responds to `inspect ping`, and the dispatcher is running. Logs use IDs and safe errors rather than raw source bodies or prompts. For capacity, use read-only SQL against the selected database; do not run these queries in a browser or expose their full output publicly:

```sh
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT status, count(*) FROM ingestion_runs GROUP BY status ORDER BY status"'
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT artifact_state, count(*) FROM documents GROUP BY artifact_state ORDER BY artifact_state"'
```

The [API reference](../api/reference.md) documents paginated project-scoped run and schedule reads. For full read-only capacity, retention, stale-age and integrity queries, use the repository's `docs/operations.sql` **on a restored copy** when investigating corruption. Monitor PostgreSQL, the document volume, Redis, worker memory (the Compose worker limit is 768 MiB), OCR page/pixel/time budgets and provider rates. Known provider usage and unknown dollar cost are different states; do not turn unknown into zero.

## Recover delivery safely

1. Inspect the affected run ID, stage, item progress and last update. A queued job during Redis/worker outage remains visible and cancellable; it has not succeeded merely because the API accepted it.
2. Check `docker compose ps` and worker/dispatcher logs. If the dispatcher alone stopped, run `docker compose up -d dispatcher` after fixing its cause. It relays queued rows and recovers stale processing, index, ingestion and preview work with bounded attempts and fenced execution tokens.
3. If a run is terminally failed or cancelled, keep that immutable record. Correct the cause, then start a new run from the exact retained artifact or source snapshot when permitted. A prior ready index remains queryable until a complete replacement publishes.

Enabled ingestion schedules have a minimum 15-minute interval. In the saved ingestion editor, select **Automatic sync → Saved schedules → Pause sync** before maintenance; one dispatcher is the normal topology. A missed due time coalesces rather than replaying every missed interval. In-flight provider calls may finish after cancellation, so inspect item states and costs before retrying. Never edit `running` to `succeeded`, copy execution tokens, delete an apparent orphan or point a collection at a partial index by hand. If a database/artifact integrity query is nonzero, stop writers and [restore a copy](./backup-restore.md) for diagnosis.

If worker ping fails, check Redis and worker startup, then retry the check before scheduling new paid work. If `/api/ready` fails, inspect migrations and PostgreSQL; restarting workers cannot repair a missing schema. If an artifact is expired or a key unavailable, a job retry will not recreate the same source revision. See [troubleshooting](./troubleshooting.md), [backup and restore](./backup-restore.md), [run ingestion](../ingestion/runs.md), and [experiment runs](../experiments/runs.md). These procedures are verified for local/isolated Compose behavior; external monitoring, rate quotas and shared operations need a separate live gate.
