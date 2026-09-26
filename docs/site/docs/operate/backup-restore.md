---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Back up and restore a workspace
slug: /operate/backup-restore/
---

Create one consistent recovery point and prove it can restore historical evidence and retained encrypted source bytes. You need operator access to PostgreSQL, the document volume and **every** wrapping-key version referenced by retained artifacts or connections. This procedure was rehearsed with fictional data in two isolated Compose projects; do not run a restore against a populated developer or shared database.

![Pause writers, capture PostgreSQL and the document volume at one recovery point, retain referenced key versions separately, then restore into an empty target and verify old and new work.](/img/recovery-checklist.svg)

<a href="/img/recovery-checklist.svg">Open the recovery checklist at full size</a>. In text: finish/cancel jobs and pause schedules, stop writers, back up PostgreSQL and document artifacts, preserve referenced keys in a separate secure store, restore an empty target, migrate and verify both historical evidence and a new run.

## Capture a local recovery point

Run from the repository root. Before step 1, open each saved **Pipelines → Ingestion pipelines** version with a schedule, select **Automatic sync → Saved schedules → Pause sync**, then wait for or cancel processing, indexing and experiment jobs; confirm terminal states in the UI or API. A queued/running job is not a consistent recovery point. Keep PostgreSQL running while the API, worker and dispatcher are stopped.

```sh
BACKUP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/rag-backup.XXXXXX")
docker compose stop backend worker dispatcher
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP_DIR/postgres.dump"
docker compose run --rm --no-deps -v "$BACKUP_DIR:/backup" backend \
  sh -c 'tar -C /data/documents -cpf /backup/documents.tar .'
docker compose exec -T db pg_restore -l < "$BACKUP_DIR/postgres.dump" > "$BACKUP_DIR/archive-list.txt"
docker compose up -d backend worker dispatcher
```

Expected result: nonempty `postgres.dump` and `documents.tar`, a readable archive list, and `/api/ready` returning `{"status":"ready"}` after restart. Preserve a manifest of app/migration version, time, volume and database identity, plus checksums of both files. Both archives can contain private source or derived content: restrict and encrypt backup storage. Store the connection keyring, artifact keyring or external KMS/Vault references **separately** through the operator's secret process; never put populated keys or archives in Git or the public docs. A database-only or volume-only copy cannot guarantee recovery. Missing wrapping keys make retained encrypted bytes unreadable even if both archives restore.

## Restore only into an empty target

Select a separate Compose project/host and different published ports. Confirm its database and document volume are empty before writing. Restore the exact files and key versions captured above; do not substitute today's source state for retained revisions. The tested rehearsal used `compose.e2e.yaml` plus the **test-only** `compose.index-e2e.yaml` provider override, ports 8003/8004, and an external mode-0600 test key file. Do not use that override for a deployment.

```sh
# Set RESTORE_ENV to the separately stored, target-only environment file.
# Set TARGET to a new, empty Compose project name; never use the source project.
TARGET=rag-docs-restore-dst
E2E_API_PORT=8004 docker compose --env-file "$RESTORE_ENV" -p "$TARGET" \
  -f compose.e2e.yaml -f compose.index-e2e.yaml up -d db
E2E_API_PORT=8004 docker compose --env-file "$RESTORE_ENV" -p "$TARGET" \
  -f compose.e2e.yaml -f compose.index-e2e.yaml exec -T db \
  pg_restore -U rag_e2e -d rag_e2e_test --clean --if-exists --no-owner --no-privileges --exit-on-error \
  < "$BACKUP_DIR/postgres.dump"
E2E_API_PORT=8004 docker compose --env-file "$RESTORE_ENV" -p "$TARGET" \
  -f compose.e2e.yaml -f compose.index-e2e.yaml run --build --rm --no-deps \
  -v "$BACKUP_DIR:/backup" backend sh -c 'tar -C /data/documents -xpf /backup/documents.tar'
E2E_API_PORT=8004 docker compose --env-file "$RESTORE_ENV" -p "$TARGET" \
  -f compose.e2e.yaml -f compose.index-e2e.yaml run --build --rm migrate
E2E_API_PORT=8004 docker compose --env-file "$RESTORE_ENV" -p "$TARGET" \
  -f compose.e2e.yaml -f compose.index-e2e.yaml up -d redis backend worker dispatcher
curl --fail http://127.0.0.1:8004/api/ready
```

The fixed `rag_e2e` database role in this **isolated rehearsal** comes from `compose.e2e.yaml`; use the selected target's role in a real recovery. `docs/site/scripts/rehearse_restore.py` refuses a non-fixture API. Its `seed` mode creates a synthetic encrypted Orchard upload, ready index and cited query; after the archive transfer, `verify` checks the same IDs and historical evidence, rewraps the retained artifact, reprocesses it to prove decryption and confirms the old index remains ready. Run it only with an isolated test-provider API and an ID record outside the repository.

If `pg_restore` fails, leave the target stopped and inspect the error and version/extension compatibility; never run `--clean` against a populated source. If `/api/ready` fails, check migrations and target database schema. If historical evidence loads but reprocessing returns 410/503, check the artifact volume, retention state and referenced key version before any retry. An expired raw artifact cannot be reconstructed from a current remote source and called the same revision. Stop a rehearsal with `docker compose ... down` **without `-v`**; named volumes remain available for inspection. See [operations](./operations.md), [security](./security.md), [versions](../concepts/versions.md), and [current limits](../reference/limits-faq.md). This local-keyring recovery was verified; external KMS/Vault restore and shared disaster recovery were not live-tested.
