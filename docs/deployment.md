# Deployment

The default verified deployment is the local Docker Compose workspace documented in the [README](../README.md). Its published ports bind to `127.0.0.1`, and local authentication provides one loopback-only owner. Shared mode requires OIDC signature/issuer/audience validation, project roles and an external AWS KMS or Vault Transit artifact-key boundary; incomplete settings fail startup. Ingress/TLS, identity provisioning and external key-service availability remain operator responsibilities. Follow the [authorization and recovery gate](operations.md) before shared access.

## PDF extraction and OCR capacity

The backend and worker images pin PyMuPDF, Pillow and the Debian Tesseract CLI with the
English trained-data pack. Extraction and OCR run in workers, not the API process. The
capability endpoint is authoritative for selectable profiles, table modes and installed
content languages; Tesseract's internal orientation data is not a selectable content
language. Install and pin another trained-data pack in every worker image before making
that language available.

Schema-v2 extraction enforces saved page, rendered-pixel, per-page timeout and output
bounds. Size worker concurrency and memory for the configured DPI and page limit, and
prefer Auto OCR so native pages avoid OCR work. Monitor extraction/OCR durations,
quality warnings and temporary-storage capacity without logging document text. A parser
or OCR failure cannot replace the current ready index; investigate and retry against a
new immutable run while the prior ready version remains queryable. Docling is not part
of the deployed runtime because its evaluated model/runtime footprint did not meet the
current deterministic offline and worker-memory gate.

Migration `0018` adds immutable Website source snapshots and exact membership, plus nullable lineage on historical ingestion runs and indexes. Apply it with the normal one-shot migration service before starting updated API/workers. The upgrade backfills only provable one-to-one historical Website lineage; null means unavailable, not an empty snapshot. The downgrade preserves existing indexes, queries, experiments, and artifacts but removes snapshot catalog data, so take a PostgreSQL backup first and roll backend/frontend/worker code together. Snapshot membership references immutable source revisions and raw artifacts; back up PostgreSQL and the document volume at one recovery point. There is no snapshot deletion or automatic retention job.

## Raw artifact encryption, identity and retention

For local development, generate a distinct 32-byte key, enable artifact encryption,
and configure a short immutable version in `ARTIFACT_ACTIVE_KEY`/`ARTIFACT_KEYS`.
Connection-vault and artifact keys are separate. New artifacts receive per-artifact
AES-256-GCM data keys and a retention deadline; the dispatcher performs fenced expiry.
Use the project document rewrap endpoint after activating a replacement key and retain
the prior version until the operational key-inventory query reaches zero.

OIDC/shared mode refuses disabled encryption and `local-keyring`. For AWS KMS set
`ARTIFACT_ENCRYPTION_MODE=kms`, map logical versions to symmetric key IDs/aliases in
`ARTIFACT_KEY_REFERENCES`, and optionally set the region. Runtime IAM needs only the
scoped `kms:Encrypt` and `kms:Decrypt` permissions for those keys; encryption context is
mandatory on both operations. For Vault set `ARTIFACT_ENCRYPTION_MODE=vault`, an HTTPS
`ARTIFACT_VAULT_ADDRESS`, token, Transit mount and logical-version-to-key-name map. The
Vault policy needs only Transit encrypt/decrypt on the named key. Do not enable
convergent encryption; the application supplies authenticated associated data and keeps
source content out of KMS/Vault. See [AWS KMS encryption contexts](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html)
and [Vault Transit HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/transit).

OIDC membership provisioning is application data: project creators become owners;
owners/admins may inspect protected content, editors may change ordinary project data,
and viewers are read-only. Audit events record protected access outcomes. Back up OIDC
subject mappings and memberships with PostgreSQL, and complete the synthetic
authorization/tamper/retention gate before shared access.

## Source connection vault

Source connections are disabled by default. To enable them locally:

1. Generate a 32-byte key with `openssl rand -base64 32`.
2. Set `SOURCE_CONNECTION_KEYS` to a JSON map such as `{"local-v1":"<generated value>"}`.
3. Set `SOURCE_CONNECTION_ACTIVE_KEY=local-v1` and `SOURCE_CONNECTIONS_ENABLED=true`.
4. Restart backend and worker processes, then verify Settings reports the vault as available.

Keys are server secrets. Do not commit them, place them in `VITE_*`, browser storage, URLs, logs or database backups. Back up the keyring separately from PostgreSQL with access controls appropriate to credentials; database ciphertext cannot be recovered after its referenced key is lost. A PostgreSQL restore must be paired with the key versions that existed when the backup was taken.

To rotate the encryption key, add a newly generated version without removing the old version, make the new version active and restart services. Use **Re-encrypt with active key** for every stored connection. Confirm no rows retain the old version before deleting it:

```sql
SELECT key_version, count(*) FROM source_connections GROUP BY key_version;
```

Credential rotation is separate: **Rotate credentials** replaces the provider credential under the active encryption key and returns the connection to `untested`. S3 testing performs a bounded `ListBuckets` request, Notion retrieves the integration bot identity, and Confluence lists at most one accessible space through REST API v2.

For Notion, create an internal integration with read-content capability and explicitly share only the pages or data sources intended for ingestion. The integration can read shared descendants according to Notion's access rules; review those descendants before a run. Do not grant update or insert capabilities. Removing a page from the integration can surface as Notion's safe not-found response and fails a required explicit selection; a later complete workspace/data-source discovery records previously indexed absent pages as removed without deleting historical revisions. Rotate the Notion token separately from the AES key and retest it before refreshing an index.

The API enforces a local Host/Origin boundary and the supplied Compose file uses loopback port bindings. Those checks are defense in depth, not identity. A shared or public deployment must add authenticated users and server-side project authorization before connection routes can be enabled or the local boundary can be changed.

## Amazon S3 source access

Use a dedicated read-only IAM principal for each intended scope. Connection testing currently requires `s3:ListAllMyBuckets`. Preview and ingestion require `s3:ListBucket` on the bucket and `s3:GetObject`; versioned exact fetches additionally require `s3:GetObjectVersion` for the selected prefix. Do not grant write, delete, ACL or bucket-policy permissions. Where practical, constrain `s3:ListBucket` with an `s3:prefix` condition and constrain object actions to `arn:aws:s3:::BUCKET/PREFIX*`. Configure the expected 12-digit bucket-owner account in the source node to protect against an unintended same-name target.

Enable bucket versioning when immutable provider revisions matter. Versioned objects are fetched by the discovered VersionId. Without versioning, ingestion relies on an ETag precondition plus size/last-modified verification; multipart ETags are treated only as opaque revision components, never as content hashes. Glacier and Deep Archive objects must be restored before they can be included.

Every source sets explicit maximum objects, list pages, bytes per object, total bytes and request timeout. SDK retries are standard mode with at most three total attempts. Choose limits below worker time limits and AWS request budgets. A refresh retains raw immutable artifacts, extracted documents, chunks and older index versions, so storage grows with changed source content; include the document volume and PostgreSQL in backup/capacity planning. There is no automatic historical-revision deletion. Rotate AWS credentials independently from AES key re-encryption, test the replacement, and retain the prior ready index until a refresh completes.

## Scheduled ingestion operations

Schedules are disabled until a user explicitly enables each one. Keep exactly one dispatcher service running in normal deployments; PostgreSQL claims and destination constraints tolerate duplicate dispatchers, but extra processes add needless polling. Provider limits still apply to scheduled work: stagger broad S3, Notion and Confluence schedules, choose conservative connector request/page bounds, and inspect throttled/failed outcomes before increasing frequency. The minimum interval is 15 minutes.

Before maintenance, pause schedules in each pipeline and wait for queued/running ingestion jobs to finish or cancel them. Back up PostgreSQL and the document volume as one recovery point; the database holds schedule/run/index membership while the volume holds immutable source artifacts. Back up the AES-256-GCM keyring separately and retain every key version referenced by `source_connections`. Restore all three components, apply `alembic upgrade head`, then start the dispatcher; overdue schedules coalesce to one attempt.

Storage grows for every changed source revision and published index. Encrypted raw artifacts use the configured retention deadline and fenced cleanup; redacted derivations, immutable versions, historical runs and indexes remain. Legacy plaintext and historical derived data are not automatically deleted. Monitor PostgreSQL, the document volume and provider costs with the [documented queries](operations.sql). Pausing a schedule stops future automatic runs but does not delete history. Never use `docker compose down -v` for routine maintenance or backup.

The released ingestion phases have deterministic end-to-end coverage for every connector and file adapter, but that does not prove a particular external account, permission set, network path or provider uptime. Treat bounded live commands as explicit, separately authorized operational checks. Do not copy test-provider overrides into a deployment or describe a local loopback stack as a verified shared production deployment.
