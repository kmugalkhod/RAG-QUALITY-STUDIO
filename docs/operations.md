# Ingestion operations

These procedures apply to the local Docker Compose deployment. Shared deployment is
allowed only with `AUTH_MODE=oidc`, validated issuer/audience/JWKS settings and an
external KMS/Vault artifact-key boundary. The application refuses an incomplete OIDC
configuration and refuses local-keyring artifact wrapping in OIDC mode.

## Health and capacity

Use application-owned status before inspecting infrastructure:

```sh
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/ready
curl --fail http://127.0.0.1:8000/api/projects/PROJECT_ID/ingestion-capabilities
docker compose ps
docker compose exec worker celery -A app.workers.celery_app:celery inspect ping
docker compose logs --since=30m backend worker dispatcher
```

`/api/health` proves only that the API process is alive. `/api/ready` checks the
database and current protected-artifact/authentication schema. The capabilities response
is authoritative for installed OCR languages, page/pixel limits and released formats.
Never infer an installed OCR language from a saved pipeline. Keep worker concurrency
within the 768 MiB Compose limit; OCR page pixels, time, output and page count are
independently bounded. Logs intentionally omit source bodies, prompts and detected
sensitive values.

Useful PostgreSQL capacity queries are in [operations.sql](operations.sql). They report
counts and byte totals only. Provider cost remains unknown unless a provider returned a
recorded amount; unknown is never converted to zero.

## Consistent backup and restore

A recoverable backup contains four coordinated components: PostgreSQL, the document
volume, the source-connection keyring and every raw-artifact wrapping-key version still
referenced by the database. Store keyrings separately from the database/artifact backup.
Losing a wrapping key is intentional cryptographic erasure and cannot be repaired.

1. Pause ingestion schedules. Let active processing/index/experiment jobs finish or
   cancel them and verify their terminal states.
2. Stop writers while retaining PostgreSQL:

   ```sh
   docker compose stop frontend backend worker dispatcher
   mkdir -p backups/RECOVERY_POINT
   docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/RECOVERY_POINT/postgres.dump
   docker compose run --rm --no-deps -v "$PWD/backups/RECOVERY_POINT:/backup" backend sh -c 'tar -C /data/documents -cpf /backup/documents.tar .'
   ```

3. Copy the external secret-store/keyring versions and the non-secret deployment
   configuration into the recovery point using the operator's approved secret process.
   Do not place populated keys in Git.
4. Restart with `docker compose up -d backend worker dispatcher` and unpause schedules
   only after readiness.

Restore only into an empty, explicitly selected deployment. Keep services stopped,
restore `documents.tar` into the empty document volume, restore the database with
`pg_restore --clean --if-exists`, restore all referenced key versions, run
`docker compose run --rm migrate`, then start the backend and workers. Verify a retained
raw artifact can be previewed, an expired artifact is reported unavailable, a historical
ready index can answer a deterministic query, and a new run publishes atomically before
accepting writes. Never use `docker compose down -v` as a backup or routine reset.

## Retention, deletion and historical evidence

New encrypted artifacts receive an immutable retention deadline (30 days by default).
The dispatcher claims expired rows with a database fence, stages and removes ciphertext,
clears the wrapped data key, and marks the artifact `deleted`. This is cryptographic
erasure: protected pre-redaction blocks and full diffs become unavailable. Redacted
derivations, chunks, index membership, query evidence, experiments and provenance stay
queryable. Automatic cleanup never deletes legacy plaintext artifacts; migrate or
manually retire those before shared deployment.

Document deletion remains blocked while work is active or while immutable ingestion/index
history references the document. Deleting or expiring raw bytes must never cascade into
historical indexes or experiment evidence. Inspect `artifact_state`,
`raw_retained_until`, `raw_deleted_at` and referenced key versions with
[operations.sql](operations.sql).

For a wrapping-key rotation, add the new version, make it active and retain all old
versions while rows still reference them. Rewrap data keys without rewriting artifact
ciphertext, verify the old-version count reaches zero, take a new recovery point, then
retire the old key. A compromised key is an incident: stop writes, revoke external
access, rewrap unaffected retained artifacts under a replacement key, expire artifacts
that cannot be trusted and preserve the audit trail.

## Stale jobs, derivations and orphan storage

The dispatcher recovers fenced processing/index/ingestion jobs whose heartbeat is stale;
duplicate delivery cannot publish twice. First inspect the status/age queries, then check
worker and Redis health. Restart the dispatcher to resume safe claims. Do not change a
`running` row to `succeeded`, copy execution tokens or repoint a current-ready index by
hand. If recovery retries are exhausted, retain the failed run and create a new immutable
run from the exact retained artifact/snapshot.

Derivations are committed with their processing run. A derivation for a missing run, a
chunk span without its cleaned derivation, or a ready index with incomplete membership
is corruption: stop writers, preserve a backup, run the full PostgreSQL tests against a
restored copy and repair through a reviewed migration. Do not delete rows until their
historical query/experiment references are understood.

Inspect filesystem orphans offline while backend/worker/dispatcher are stopped:

1. Export `SELECT storage_name FROM documents WHERE artifact_state <> 'deleted' ORDER BY
   storage_name` to a file.
2. List only regular files in the document volume. Ignore bounded parser temp files only
   after confirming no worker is running.
3. Compute the set difference. Files absent from the database may result from an
   ambiguous upload commit; database names absent from storage are data loss unless the
   row is `deleted`.
4. Move suspected orphan files to a quarantined backup location. Do not erase them until
   a second database/artifact backup and ownership review are complete.

## Dependency/model upgrades and rollback

Parser, OCR trained-data, tokenizer, detector or model changes require a new stable
runtime identity. Build an isolated stack, run the complete backend suite (including real
Tesseract and PostgreSQL), regenerate the reviewed corpus report and compare blocks,
reading order, tables, OCR ground truth, cleaning removals, chunk spans, latency bands,
failures and hashes. Expectation changes require human review; never update fixtures only
to make a regression pass. Publish new pipeline/index versions rather than rewriting old
derivations.

Before rollout, back up all four components and verify downgrade/upgrade migrations on a
populated copy. Roll backend, worker and dispatcher together. If a release regresses,
stop new work and roll application code back while keeping the newer additive database
schema unless a tested downgrade is required. Existing v1 and earlier v2 ready indexes
remain queryable because query evidence uses immutable chunks and index membership, not
raw reparsing. A code rollback cannot create or edit newer format/policy configurations;
leave them historical and create no replacement under older semantics. Never expose a
partial or failed index as current during rollback.

## Shared-deployment authorization gate

Before shared access, verify OIDC signature, issuer, audience, expiry and subject checks;
owner/admin/editor/viewer project isolation; viewer write denial; owner/admin-only
protected reads; denied and granted sensitive-read audit events; and absence of source
values from logs, URLs, browser storage and error bodies. Run the synthetic authorization,
artifact tamper/retention and sensitive-data suites. Local mode is one loopback owner and
is not a shared-deployment substitute.
