---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Datasets and experiments
slug: /api/reference/evaluation/
---

Import a reviewed dataset, submit a versioned comparison and inspect each result and aggregate.

**Prerequisite:** Set PROJECT_ID to an authorized project; evaluator execution needs saved answer versions and configured server-side providers. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/datasets/example.csv"
```

**Expected result:** A UTF-8 CSV example with the current accepted headers is returned. **If it fails:** For 409 after import, preview the same file again; for failed experiment items, inspect reasons before scheduling another paid run.

**Capability boundary:** Deterministic local orchestration is tested; live RAGAS judgments and paid evaluator costs need separate authorization. Related: [Datasets](../../experiments/datasets.md), [Run experiments](../../experiments/runs.md), [Metrics](../../experiments/metrics.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/projects/{project_id}/datasets/example.csv`

OpenAPI operation ID: `example_api_projects__project_id__datasets_example_csv_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `text/csv` string |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/datasets/preview`

OpenAPI operation ID: `preview_api_projects__project_id__datasets_preview_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `multipart/form-data` [`Body_preview_api_projects__project_id__datasets_preview_post`](../schema-models.md#body_preview_api_projects__project_id__datasets_preview_post). Required.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/datasets`

OpenAPI operation ID: `upload_api_projects__project_id__datasets_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `multipart/form-data` [`Body_upload_api_projects__project_id__datasets_post`](../schema-models.md#body_upload_api_projects__project_id__datasets_post). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`DatasetRead`](../schema-models.md#datasetread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/datasets`

OpenAPI operation ID: `list_datasets_api_projects__project_id__datasets_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/datasets/{version_id}`

OpenAPI operation ID: `dataset_api_projects__project_id__datasets__version_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `version_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`DatasetRead`](../schema-models.md#datasetread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/experiments/options`

OpenAPI operation ID: `options_api_projects__project_id__experiments_options_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/experiments`

OpenAPI operation ID: `create_api_projects__project_id__experiments_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`ExperimentCreate`](../schema-models.md#experimentcreate). Required.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`ExperimentRead`](../schema-models.md#experimentread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/experiments`

OpenAPI operation ID: `listing_api_projects__project_id__experiments_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/experiments/{experiment_id}`

OpenAPI operation ID: `detail_api_projects__project_id__experiments__experiment_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `experiment_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/experiments/{experiment_id}/cancel`

OpenAPI operation ID: `cancel_api_projects__project_id__experiments__experiment_id__cancel_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `experiment_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ExperimentRead`](../schema-models.md#experimentread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/experiments/{experiment_id}/export.csv`

OpenAPI operation ID: `export_api_projects__project_id__experiments__experiment_id__export_csv_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `experiment_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `text/csv` string |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
