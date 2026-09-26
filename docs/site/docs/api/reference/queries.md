---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Answer query runs
slug: /api/reference/queries/
---

List persisted answer runs and inspect the exact version, evidence and status of a question.

**Prerequisite:** Set PROJECT_ID to an authorized project; a submitted question needs a ready index and answer provider. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/query-runs?limit=20&offset=0"
```

**Expected result:** The response contains paginated saved runs, including failed or insufficient-evidence states. **If it fails:** If execution fails, inspect the safe error and submit a new question after correction; this path has no cancellation endpoint.

**Capability boundary:** Answer generation can incur provider charges; unknown dollar cost is not zero. Related: [Playground](../../answers/playground.md), [Past questions](../../answers/history.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### POST `/api/projects/{project_id}/query-runs`

OpenAPI operation ID: `execute_api_projects__project_id__query_runs_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`QueryRequest`](../schema-models.md#queryrequest). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`QueryRead`](../schema-models.md#queryread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/query-runs`

OpenAPI operation ID: `list_runs_api_projects__project_id__query_runs_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`QueryPage`](../schema-models.md#querypage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/query-runs/{run_id}`

OpenAPI operation ID: `get_run_api_projects__project_id__query_runs__run_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `run_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`QueryRead`](../schema-models.md#queryread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
