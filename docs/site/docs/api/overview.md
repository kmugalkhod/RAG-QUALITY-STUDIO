---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: API overview
slug: /api/overview/
---

Discover the current local HTTP contract before integrating. OpenAPI generation and `/openapi.json` now pass a regression check at commit `481b4eca90c5` plus this branch's schema fix, reviewed 2026-09-26. Endpoint behavior is versioned by the server's schema and saved resource IDs; there is no separate `/v1` path in this release.

## Prerequisites and authentication

Start the [local stack](../start/install.md). In default `AUTH_MODE=local`, the API accepts loopback requests as one owner. This is for local development only. Configured `AUTH_MODE=oidc` validates bearer tokens against issuer, audience and HTTPS JWKS, then checks project roles; it also requires encrypted raw artifacts with an external KMS/Vault key boundary. The OpenAPI schema does not fully express these dependency-based security rules, so consult the operator configuration before shared use. Shared deployment has not passed a live release gate.

## Discover and check

```sh
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/ready
curl --fail http://127.0.0.1:8000/openapi.json -o /tmp/rag-quality-studio-openapi.json
```

Expected result: health returns `status: ok`, readiness returns `status: ready`, and the JSON file contains `paths` and `components.schemas`. Open [the interactive schema](http://127.0.0.1:8000/docs) on the local backend to inspect exact request fields. Health does not depend on the database; readiness does. If readiness returns 503, inspect migration/database service status. If OIDC returns 401/403, check the token and project membership rather than retrying a write anonymously.

Use [API patterns](./patterns.md) for pagination, job polling, errors and costs, [the grouped endpoint reference](./reference.md) for generated paths, media types and schemas, and [workflow recipes](./recipes.md) for tested request order. The checked public [`openapi.json`](/openapi.json) comes from `app.openapi()`; the running backend remains authoritative if its version differs. No paid or external call is made by the read-only commands above.
