---
verified_against: "481b4eca90c5 + docs phase 1 working tree (2026-09-26)"
title: API patterns and versioned jobs
slug: /api/patterns/
---

Create a synthetic local project, paginate the list, and handle asynchronous work without losing version identity. Applies to the current API at commit `481b4eca90c5` plus the OpenAPI fix, reviewed 2026-09-26. The commands below use local owner mode only.

## Prerequisites

Start the [local stack](../start/install.md). Use an isolated project name. In OIDC mode, send `Authorization: Bearer <token>` from a permitted client and ensure project membership; do not put tokens in a URL or checked-in shell script. Open [the generated endpoint contracts](./reference.md) and [validated OpenAPI schema](/openapi.json) for exact body/response fields before a write.

```sh
curl --fail -H 'Content-Type: application/json' \
  -d '{"name":"Harbor API example"}' \
  http://127.0.0.1:8000/api/projects
curl --fail 'http://127.0.0.1:8000/api/projects?limit=20&offset=0'
```

Expected result: create returns HTTP 201 with a project `id`; list returns `items`, `total`, `limit` and `offset`. Use the returned ID in later project-scoped paths, never an invented one. Collections have bounded pagination. A 422 response carries a safe `detail` array of `loc`, `msg` and `type`; it omits submitted input. Missing or forbidden project access returns an appropriate 401/403/404 depending on mode and resource, while database/provider unavailability can return 503. Do not retry a non-idempotent POST blindly after a timeout: list or fetch the resource first to see whether it was accepted.

Document processing, indexing, ingestion and experiments return a job or run record promptly; poll its project-scoped GET route until a terminal state, inspect failed/skipped items and keep the exact saved pipeline/index/dataset version IDs. Queue wait, indexing, query and evaluation latency are distinct. Provider charges may occur even if a later stage fails; unknown cost is not zero. If a job stalls, inspect the worker/dispatcher and its status before creating another run. Continue with [versions](../concepts/versions.md) or [the local workflow](../start/first-workflow.md). This page does not claim a live provider or shared OIDC deployment was exercised.
