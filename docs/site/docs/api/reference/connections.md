---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Source connections
slug: /api/reference/connections/
---

Discover vault availability and manage opaque connection records without reading stored credentials.

**Prerequisite:** Set PROJECT_ID to an authorized project. Connection writes require the configured encrypted vault and appropriate role. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/source-connections/settings"
```

**Expected result:** The response reports safe vault availability and connection kinds, not secret values. **If it fails:** If disabled or unavailable, configure the server-side keyring; do not put a secret in a URL or docs example.

**Capability boundary:** S3, Notion and Confluence real-account permissions require separate live checks. Related: [Source connections](../../ingestion/connections.md), [Security limits](../../reference/limitations.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/projects/{project_id}/source-connections/settings`

OpenAPI operation ID: `read_settings_api_projects__project_id__source_connections_settings_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceConnectionSettings`](../schema-models.md#sourceconnectionsettings) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-connections`

OpenAPI operation ID: `list_connections_api_projects__project_id__source_connections_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceConnectionPage`](../schema-models.md#sourceconnectionpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/source-connections`

OpenAPI operation ID: `create_connection_api_projects__project_id__source_connections_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`SourceConnectionCreate`](../schema-models.md#sourceconnectioncreate). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`SourceConnectionRead`](../schema-models.md#sourceconnectionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-connections/{connection_id}`

OpenAPI operation ID: `read_connection_api_projects__project_id__source_connections__connection_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `connection_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceConnectionRead`](../schema-models.md#sourceconnectionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/source-connections/{connection_id}/test`

OpenAPI operation ID: `test_connection_api_projects__project_id__source_connections__connection_id__test_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `connection_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceConnectionRead`](../schema-models.md#sourceconnectionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/source-connections/{connection_id}/rotate`

OpenAPI operation ID: `rotate_connection_api_projects__project_id__source_connections__connection_id__rotate_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `connection_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`SourceConnectionRotate`](../schema-models.md#sourceconnectionrotate). Required.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceConnectionRead`](../schema-models.md#sourceconnectionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/source-connections/{connection_id}/rewrap`

OpenAPI operation ID: `rewrap_connection_api_projects__project_id__source_connections__connection_id__rewrap_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `connection_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceConnectionRead`](../schema-models.md#sourceconnectionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
