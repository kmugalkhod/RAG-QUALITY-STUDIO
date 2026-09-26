---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Projects and access
slug: /api/reference/projects/
---

Create, list and read a project and inspect the current principal's project access.

**Prerequisite:** Use the local loopback owner mode or a permitted OIDC token; project writes are scoped by the server. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail 'http://127.0.0.1:8000/api/projects?limit=20&offset=0'
```

**Expected result:** A paginated object with items, total, limit and offset is returned. **If it fails:** For 401/403/404, check authentication and project membership; do not substitute another project's ID.

**Capability boundary:** Local ownership is tested; live shared OIDC acceptance remains a separate release gate. Related: [Projects](../../concepts/projects.md), [API patterns](../patterns.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/projects`

OpenAPI operation ID: `list_projects_api_projects_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ProjectPage`](../schema-models.md#projectpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects`

OpenAPI operation ID: `create_project_api_projects_post`.

**Request body:** `application/json` [`ProjectCreate`](../schema-models.md#projectcreate). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`ProjectRead`](../schema-models.md#projectread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/access`

OpenAPI operation ID: `project_access_api_projects__project_id__access_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}`

OpenAPI operation ID: `get_project_api_projects__project_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ProjectRead`](../schema-models.md#projectread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
