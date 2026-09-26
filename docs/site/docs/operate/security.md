---
verified_against: "481b4eca90c5 + docs phase 4 working tree (2026-09-26)"
title: Security and permissions
slug: /operate/security/
---

Check whether a workspace can safely remain local or proceed to a separately validated shared-access gate. You need operator access to server configuration and an isolated test database for the synthetic checks below. Do not paste tokens, connection credentials, raw source text or encryption keys into commands, browser storage, URLs or issue reports.

![Local loopback requests and configured OIDC requests enter project authorization; owner and admin can read protected raw content, while encrypted artifacts and connection credentials have separate key boundaries.](/img/security-boundary.svg)

<a href="/img/security-boundary.svg">Open the trust-boundary diagram at full size</a>. In text: local mode has one loopback owner; shared mode validates bearer tokens before project membership; protected source reads have an owner/admin audit gate; artifacts and source credentials use separate encryption keys.

## Current enforcement

| Operation | Current rule |
| --- | --- |
| Local request | `AUTH_MODE=local` treats a loopback Host as one owner. It is not multi-user authentication. |
| Shared request | `AUTH_MODE=oidc` checks bearer signature, issuer, audience, expiry and subject against configured HTTPS JWKS. An unrelated project returns 404; a viewer write returns 403. |
| Ordinary project read/write | Owner, admin, editor and viewer can read their project; viewer writes are denied. Do not infer access to another project from a known UUID. |
| Protected raw/derivation read or artifact rewrap | Owner or admin only; granted and denied attempts create a `sensitive_access_events` audit row without source values. |
| Source-connection management | Disabled by default; when enabled, a separate AES-256-GCM keyring and loopback Host/Origin boundary guard credentials. Reads expose redacted metadata. A shared ingress cannot use these credentialed routes as currently guarded. |
| New raw artifacts | Optional encrypted local storage; required in OIDC mode with external KMS/Vault wrapping. Default retention is 30 days for new encrypted raw artifacts. Expiry removes ciphertext and wrapped key but retains redacted derivations, indexes and historical evidence. Legacy plaintext needs separate migration/retirement review. |

Website fetching validates public HTTP(S) destinations, DNS results and redirects and applies page/size/time/origin limits. Treat retrieved text as untrusted content; source instructions do not become application commands. Sensitive-data detectors and redaction reduce exposure, but cannot guarantee finding every private value. The selected policy must redact or exclude before embedding; review findings and the published evidence on a synthetic source. See [cleaning and sensitive data](../ingestion/cleaning.md) and [source connections](../ingestion/connections.md).

## Run the local security gate

From the repository root, use the dedicated `compose.test.yaml` PostgreSQL test database, not the development volume:

```sh
docker compose -p rag-docs-security -f compose.test.yaml run --build --rm tests \
  python -m pytest -q tests/test_security_controls.py tests/test_artifact_security.py tests/test_connections.py
docker compose -p rag-docs-security -f compose.test.yaml down
```

Expected result: synthetic OIDC claims, cross-project/viewer denial, protected-read audit, artifact tamper/expiry and connection encryption checks pass against isolated PostgreSQL where required. The test stack's database uses tmpfs; `down` here does not touch development volumes. Test-only keys and provider doubles in tests are not deployable credentials. A failing check blocks shared-access claims; fix the cause and rerun against a fresh isolated database. For an actual shared deployment, also verify real token provisioning and revocation, TLS ingress, KMS/Vault availability and restore of referenced key versions before admitting users. That live gate has not been run for this site.

If an API returns 401, validate bearer presence and issuer/audience/expiry without logging the token. For 403, inspect the user's project role or protected-read requirement; for 404, confirm project membership and resource ID without disclosing another project's existence. For a 503 on encrypted storage, restore the referenced key service/version rather than reuploading or deleting the record. See [deployment](./deploy.md), [backup and restore](./backup-restore.md), [troubleshooting](./troubleshooting.md), and [API authentication](../api/overview.md). These steps apply to the current local code and synthetic security tests; an external identity or key service requires its own authorized acceptance.
