---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Ingestion previews, runs and snapshots
slug: /api/reference/ingestion/
---

Inspect capabilities, preview processing, run a saved version and trace the exact source snapshot.

**Prerequisite:** Set PROJECT_ID to an authorized project. Remote collection additionally needs a permitted source and possibly a server-side connection. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/ingestion-capabilities"
```

**Expected result:** The response states installed extraction and OCR capabilities for this backend. **If it fails:** Inspect terminal run/item states, expiry or permission errors before retrying; never treat a partial index as ready.

**Capability boundary:** Synthetic local/controlled transport paths are tested; live remote accounts and paid embedding runs are not implied. Related: [Preview processing](../../ingestion/previews.md), [Run ingestion](../../ingestion/runs.md), [Source history](../../ingestion/source-history.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/projects/{project_id}/ingestion-capabilities`

OpenAPI operation ID: `capabilities_api_projects__project_id__ingestion_capabilities_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ExtractionCapabilities`](../schema-models.md#extractioncapabilities) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/ingestion-previews`

OpenAPI operation ID: `preview_api_projects__project_id__ingestion_previews_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`IngestionPreviewRequest`](../schema-models.md#ingestionpreviewrequest). Required.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`SourcePreviewRead`](../schema-models.md#sourcepreviewread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-previews/{preview_id}`

OpenAPI operation ID: `get_preview_api_projects__project_id__source_previews__preview_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `preview_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourcePreviewRead`](../schema-models.md#sourcepreviewread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-previews/{preview_id}/items`

OpenAPI operation ID: `preview_items_api_projects__project_id__source_previews__preview_id__items_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `preview_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourcePreviewItemPage`](../schema-models.md#sourcepreviewitempage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-previews/{preview_id}/items/{item_ordinal}/representations`

OpenAPI operation ID: `preview_representations_api_projects__project_id__source_previews__preview_id__items__item_ordinal__representations_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `preview_id` | path | yes | string (uuid) | — |
| `item_ordinal` | path | yes | integer | — |
| `stage` | query | yes | string: raw, extracted, cleaned, diff, chunks | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourcePreviewRepresentationPage`](../schema-models.md#sourcepreviewrepresentationpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/source-previews/{preview_id}/cancel`

OpenAPI operation ID: `cancel_preview_api_projects__project_id__source_previews__preview_id__cancel_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `preview_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourcePreviewRead`](../schema-models.md#sourcepreviewread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/source-previews/{preview_id}/retry`

OpenAPI operation ID: `retry_preview_api_projects__project_id__source_previews__preview_id__retry_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `preview_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`SourcePreviewRead`](../schema-models.md#sourcepreviewread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/pipelines/{pipeline_id}/versions/{version_id}/ingestion-runs`

OpenAPI operation ID: `start_run_api_projects__project_id__pipelines__pipeline_id__versions__version_id__ingestion_runs_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `pipeline_id` | path | yes | string (uuid) | — |
| `version_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`IngestionRunStart`](../schema-models.md#ingestionrunstart) or null.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`IngestionRunRead`](../schema-models.md#ingestionrunread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/ingestion-runs`

OpenAPI operation ID: `list_runs_api_projects__project_id__ingestion_runs_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |
| `pipeline_version_id` | query | no | string (uuid) or null | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IngestionRunPage`](../schema-models.md#ingestionrunpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/ingestion-runs/{run_id}`

OpenAPI operation ID: `get_run_api_projects__project_id__ingestion_runs__run_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `run_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IngestionRunRead`](../schema-models.md#ingestionrunread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/ingestion-runs/{run_id}/items`

OpenAPI operation ID: `list_items_api_projects__project_id__ingestion_runs__run_id__items_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `run_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IngestionRunItemPage`](../schema-models.md#ingestionrunitempage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/ingestion-runs/{run_id}/cancel`

OpenAPI operation ID: `cancel_run_api_projects__project_id__ingestion_runs__run_id__cancel_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `run_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IngestionRunRead`](../schema-models.md#ingestionrunread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-snapshots`

OpenAPI operation ID: `list_source_snapshots_api_projects__project_id__source_snapshots_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceSnapshotPage`](../schema-models.md#sourcesnapshotpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-snapshots/{snapshot_id}`

OpenAPI operation ID: `get_source_snapshot_api_projects__project_id__source_snapshots__snapshot_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `snapshot_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceSnapshotRead`](../schema-models.md#sourcesnapshotread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-snapshots/{snapshot_id}/items`

OpenAPI operation ID: `list_source_snapshot_items_api_projects__project_id__source_snapshots__snapshot_id__items_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `snapshot_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceSnapshotMemberPage`](../schema-models.md#sourcesnapshotmemberpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/source-snapshots/{snapshot_id}/indexes`

OpenAPI operation ID: `list_source_snapshot_indexes_api_projects__project_id__source_snapshots__snapshot_id__indexes_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `snapshot_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SourceSnapshotIndexPage`](../schema-models.md#sourcesnapshotindexpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/ingestion-schedules`

OpenAPI operation ID: `listing_api_projects__project_id__ingestion_schedules_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`SchedulePage`](../schema-models.md#schedulepage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/ingestion-schedules`

OpenAPI operation ID: `create_api_projects__project_id__ingestion_schedules_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`ScheduleCreate`](../schema-models.md#schedulecreate). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`ScheduleRead`](../schema-models.md#scheduleread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/ingestion-schedules/{schedule_id}`

OpenAPI operation ID: `read_api_projects__project_id__ingestion_schedules__schedule_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `schedule_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ScheduleRead`](../schema-models.md#scheduleread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/ingestion-schedules/{schedule_id}`

OpenAPI operation ID: `update_api_projects__project_id__ingestion_schedules__schedule_id__post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `schedule_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`ScheduleUpdate`](../schema-models.md#scheduleupdate). Required.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ScheduleRead`](../schema-models.md#scheduleread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/ingestion-schedules/{schedule_id}/run`

OpenAPI operation ID: `run_api_projects__project_id__ingestion_schedules__schedule_id__run_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `schedule_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`IngestionRunRead`](../schema-models.md#ingestionrunread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
