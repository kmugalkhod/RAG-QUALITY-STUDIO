# Deployment

The currently verified deployment is the local Docker Compose workspace documented in the [README](../README.md). Its published ports bind to `127.0.0.1`. Authentication and multi-user authorization are not implemented, so do not expose this stack through a public ingress or shared host.

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

Credential rotation is separate: **Rotate credentials** replaces the provider credential under the active encryption key and returns the connection to `untested`. S3 connection testing performs a bounded `ListBuckets` request; Notion and Confluence testing remains unavailable until those adapters are installed.

The API enforces a local Host/Origin boundary and the supplied Compose file uses loopback port bindings. Those checks are defense in depth, not identity. A shared or public deployment must add authenticated users and server-side project authorization before connection routes can be enabled or the local boundary can be changed.

## Amazon S3 source access

Use a dedicated read-only IAM principal for each intended scope. Connection testing currently requires `s3:ListAllMyBuckets`. Preview and ingestion require `s3:ListBucket` on the bucket and `s3:GetObject`; versioned exact fetches additionally require `s3:GetObjectVersion` for the selected prefix. Do not grant write, delete, ACL or bucket-policy permissions. Where practical, constrain `s3:ListBucket` with an `s3:prefix` condition and constrain object actions to `arn:aws:s3:::BUCKET/PREFIX*`. Configure the expected 12-digit bucket-owner account in the source node to protect against an unintended same-name target.

Enable bucket versioning when immutable provider revisions matter. Versioned objects are fetched by the discovered VersionId. Without versioning, ingestion relies on an ETag precondition plus size/last-modified verification; multipart ETags are treated only as opaque revision components, never as content hashes. Glacier and Deep Archive objects must be restored before they can be included.

Every source sets explicit maximum objects, list pages, bytes per object, total bytes and request timeout. SDK retries are standard mode with at most three total attempts. Choose limits below worker time limits and AWS request budgets. A refresh retains raw immutable artifacts, extracted documents, chunks and older index versions, so storage grows with changed source content; include the document volume and PostgreSQL in backup/capacity planning. There is no automatic historical-revision deletion. Rotate AWS credentials independently from AES key re-encryption, test the replacement, and retain the prior ready index until a refresh completes.
