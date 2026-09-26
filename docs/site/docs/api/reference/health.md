---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Health and readiness
slug: /api/reference/health/
---

Distinguish a responding API process from a database and schema that can serve work.

**Prerequisite:** Start the local backend. These two reads do not need a project ID or provider credentials. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/ready
```

**Expected result:** Both return HTTP 200 with a status; readiness checks migrated database tables. **If it fails:** If readiness returns 503, inspect the database and migration services before retrying a job.

**Capability boundary:** This verifies local process/schema reachability; it does not certify provider access or shared deployment. Related: [Install locally](../../start/install.md), [API overview](../overview.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/health`

OpenAPI operation ID: `health_api_health_get`.

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |

### GET `/api/ready`

OpenAPI operation ID: `ready_api_ready_get`.

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
