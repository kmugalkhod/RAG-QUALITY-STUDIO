---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Saved pipelines
slug: /api/reference/pipelines/
---

Inspect supported answer/ingestion options and save immutable, validated pipeline versions.

**Prerequisite:** Set PROJECT_ID to an authorized project and have a compatible ready index or source configuration. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/pipelines/options"
```

**Expected result:** The server reports configured options and availability without returning credentials. **If it fails:** On 422, correct the graph or node setting; do not bypass server validation. Confirm a POST's result before retrying it.

**Capability boundary:** Only the supported graph templates execute; arbitrary nodes or code are rejected. Related: [Answer pipelines](../../answers/pipelines.md), [Ingestion pipelines](../../ingestion/pipelines.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/projects/{project_id}/pipelines/options`

OpenAPI operation ID: `options_api_projects__project_id__pipelines_options_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/pipelines/preview-runs`

OpenAPI operation ID: `preview_api_projects__project_id__pipelines_preview_runs_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`PreviewRequest`](../schema-models.md#previewrequest). Required.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`QueryRead`](../schema-models.md#queryread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/pipelines`

OpenAPI operation ID: `listing_api_projects__project_id__pipelines_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |
| `kind` | query | no | string: answer, ingestion or null | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`PipelinePage`](../schema-models.md#pipelinepage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/pipelines`

OpenAPI operation ID: `create_api_projects__project_id__pipelines_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`PipelineSave`](../schema-models.md#pipelinesave) or [`IngestionPipelineSave`](../schema-models.md#ingestionpipelinesave). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`VersionRead`](../schema-models.md#versionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/pipelines/{pipeline_id}/versions`

OpenAPI operation ID: `save_api_projects__project_id__pipelines__pipeline_id__versions_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `pipeline_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`PipelineSave`](../schema-models.md#pipelinesave) or [`IngestionPipelineSave`](../schema-models.md#ingestionpipelinesave). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`VersionRead`](../schema-models.md#versionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/pipelines/{pipeline_id}/versions`

OpenAPI operation ID: `versions_api_projects__project_id__pipelines__pipeline_id__versions_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `pipeline_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`VersionPage`](../schema-models.md#versionpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/pipelines/{pipeline_id}/versions/{version_id}`

OpenAPI operation ID: `version_api_projects__project_id__pipelines__pipeline_id__versions__version_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `pipeline_id` | path | yes | string (uuid) | — |
| `version_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`VersionRead`](../schema-models.md#versionread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/pipelines/{pipeline_id}/versions/{version_id}/runs`

OpenAPI operation ID: `run_api_projects__project_id__pipelines__pipeline_id__versions__version_id__runs_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `pipeline_id` | path | yes | string (uuid) | — |
| `version_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`RunRequest`](../schema-models.md#runrequest). Required.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`QueryRead`](../schema-models.md#queryread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
