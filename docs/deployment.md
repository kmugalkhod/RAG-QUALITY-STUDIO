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

Credential rotation is separate: **Rotate credentials** replaces the provider credential under the active encryption key and returns the connection to `untested`. Provider testing remains unavailable until that connector's real adapter is installed.

The API enforces a local Host/Origin boundary and the supplied Compose file uses loopback port bindings. Those checks are defense in depth, not identity. A shared or public deployment must add authenticated users and server-side project authorization before connection routes can be enabled or the local boundary can be changed.
