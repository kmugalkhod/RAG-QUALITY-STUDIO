---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Documents and processing
slug: /api/reference/documents/
---

Inspect upload limits, store a document and track versioned processing and canonical content.

**Prerequisite:** Set PROJECT_ID to an authorized project; uploads use multipart form data and encrypted local artifact storage. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/upload-settings"
```

**Expected result:** The response lists actual accepted formats and upload limits for this backend. **If it fails:** For 413/422, use a supported bounded file and check the safe error. A failed run does not replace a successful processing version.

**Capability boundary:** Local file processing is exercised with synthetic files; external OCR installation and protected raw reads have separate gates. Related: [Documents](../../knowledge-base/documents.md), [Prepare content](../../knowledge-base/prepare.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/projects/{project_id}/upload-settings`

OpenAPI operation ID: `upload_settings_api_projects__project_id__upload_settings_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/documents`

OpenAPI operation ID: `upload_api_projects__project_id__documents_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `multipart/form-data` [`Body_upload_api_projects__project_id__documents_post`](../schema-models.md#body_upload_api_projects__project_id__documents_post). Required.

| Response | Content contract |
| --- | --- |
| `201` | `application/json` [`DocumentRead`](../schema-models.md#documentread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/documents`

OpenAPI operation ID: `list_documents_api_projects__project_id__documents_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`DocumentPage`](../schema-models.md#documentpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### DELETE `/api/projects/{project_id}/documents/{document_id}`

OpenAPI operation ID: `remove_api_projects__project_id__documents__document_id__delete`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `document_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/documents/{document_id}/artifact/rewrap`

OpenAPI operation ID: `rewrap_artifact_api_projects__project_id__documents__document_id__artifact_rewrap_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `document_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/documents/{document_id}/runs`

OpenAPI operation ID: `start_api_projects__project_id__documents__document_id__runs_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `document_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`ProcessingConfig`](../schema-models.md#processingconfig). Required.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`RunRead`](../schema-models.md#runread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/documents/{document_id}/runs`

OpenAPI operation ID: `list_runs_api_projects__project_id__documents__document_id__runs_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `document_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`RunPage`](../schema-models.md#runpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/documents/{document_id}/runs/{run_id}`

OpenAPI operation ID: `get_run_api_projects__project_id__documents__document_id__runs__run_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `document_id` | path | yes | string (uuid) | — |
| `run_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`RunRead`](../schema-models.md#runread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/documents/{document_id}/runs/{run_id}/cancel`

OpenAPI operation ID: `cancel_api_projects__project_id__documents__document_id__runs__run_id__cancel_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `document_id` | path | yes | string (uuid) | — |
| `run_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`RunRead`](../schema-models.md#runread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/documents/{document_id}/runs/{run_id}/chunks`

OpenAPI operation ID: `chunks_api_projects__project_id__documents__document_id__runs__run_id__chunks_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `document_id` | path | yes | string (uuid) | — |
| `run_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ChunkPage`](../schema-models.md#chunkpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/processing-runs/{processing_run_id}/derivations`

OpenAPI operation ID: `list_content_derivations_api_projects__project_id__processing_runs__processing_run_id__derivations_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `processing_run_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ContentDerivationList`](../schema-models.md#contentderivationlist) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/content-derivations/{derivation_id}/blocks`

OpenAPI operation ID: `list_content_blocks_api_projects__project_id__content_derivations__derivation_id__blocks_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `derivation_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ContentBlockPage`](../schema-models.md#contentblockpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/processing-runs/{processing_run_id}/cleaning-diff`

OpenAPI operation ID: `list_cleaning_diff_api_projects__project_id__processing_runs__processing_run_id__cleaning_diff_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `processing_run_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`CleaningDiffPage`](../schema-models.md#cleaningdiffpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/processing-runs/{processing_run_id}/chunks`

OpenAPI operation ID: `list_content_chunks_api_projects__project_id__processing_runs__processing_run_id__chunks_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `processing_run_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ChunkInspectionPage`](../schema-models.md#chunkinspectionpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/processing-runs/{processing_run_id}/chunks/{chunk_ordinal}/spans`

OpenAPI operation ID: `list_content_chunk_spans_api_projects__project_id__processing_runs__processing_run_id__chunks__chunk_ordinal__spans_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `processing_run_id` | path | yes | string (uuid) | — |
| `chunk_ordinal` | path | yes | integer | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`ChunkBlockSpanList`](../schema-models.md#chunkblockspanlist) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/processing-runs/{processing_run_id}/pages/{page_number}/thumbnail`

OpenAPI operation ID: `page_thumbnail_api_projects__project_id__processing_runs__processing_run_id__pages__page_number__thumbnail_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `processing_run_id` | path | yes | string (uuid) | — |
| `page_number` | path | yes | integer | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `image/png` string (binary) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
