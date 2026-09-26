---
verified_against: "OpenAPI SHA-256 1237e6ca1816bbbde889c9a991668b9540326c4e26a77c5b9fbc2ba053206d1c (2026-09-26)"
title: Indexes and retrieval
slug: /api/reference/indexes/
---

List immutable index versions and retrieve passages from a compatible ready version.

**Prerequisite:** Set PROJECT_ID to an authorized project and publish a ready index. For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.

```sh
curl --fail "http://127.0.0.1:8000/api/projects/$PROJECT_ID/indexes?limit=20&offset=0"
```

**Expected result:** A paginated list includes index status, version and source membership metadata. **If it fails:** If retrieval returns 409, select a ready compatible index; do not query a partial or incompatible one.

**Capability boundary:** PostgreSQL/pgvector retrieval is locally tested; relevance and model cost depend on the configured provider and corpus. Related: [Collections](../../knowledge-base/collections.md), [Retrieval settings](../../answers/retrieval.md). The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.

## Operations

### GET `/api/projects/{project_id}/embedding-settings`

OpenAPI operation ID: `embedding_settings_api_projects__project_id__embedding_settings_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` object |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/indexes`

OpenAPI operation ID: `create_index_api_projects__project_id__indexes_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`IndexCreate`](../schema-models.md#indexcreate) or null.

| Response | Content contract |
| --- | --- |
| `202` | `application/json` [`IndexRead`](../schema-models.md#indexread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/indexes`

OpenAPI operation ID: `list_indexes_api_projects__project_id__indexes_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |
| `knowledge_set_id` | query | no | string (uuid) or null | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IndexPage`](../schema-models.md#indexpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/knowledge-sets`

OpenAPI operation ID: `list_knowledge_sets_api_projects__project_id__knowledge_sets_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`KnowledgeSetPage`](../schema-models.md#knowledgesetpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/knowledge-sets/{knowledge_set_id}/indexes`

OpenAPI operation ID: `list_knowledge_set_indexes_api_projects__project_id__knowledge_sets__knowledge_set_id__indexes_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `knowledge_set_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IndexPage`](../schema-models.md#indexpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/indexes/{index_id}`

OpenAPI operation ID: `get_index_api_projects__project_id__indexes__index_id__get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `index_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IndexRead`](../schema-models.md#indexread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### GET `/api/projects/{project_id}/indexes/{index_id}/records`

OpenAPI operation ID: `list_index_records_api_projects__project_id__indexes__index_id__records_get`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `index_id` | path | yes | string (uuid) | — |
| `limit` | query | no | integer | minimum=1, maximum=100, default=20 |
| `offset` | query | no | integer | minimum=0, default=0 |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IndexRecordPage`](../schema-models.md#indexrecordpage) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/indexes/{index_id}/cancel`

OpenAPI operation ID: `cancel_index_api_projects__project_id__indexes__index_id__cancel_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |
| `index_id` | path | yes | string (uuid) | — |

**Request body:** none.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`IndexRead`](../schema-models.md#indexread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |

### POST `/api/projects/{project_id}/retrieval`

OpenAPI operation ID: `retrieve_api_projects__project_id__retrieval_post`.

| Parameter | In | Required | Type | Bounds/default |
| --- | --- | --- | --- | --- |
| `project_id` | path | yes | string (uuid) | — |

**Request body:** `application/json` [`RetrievalRequest`](../schema-models.md#retrievalrequest). Required.

| Response | Content contract |
| --- | --- |
| `200` | `application/json` [`RetrievalRead`](../schema-models.md#retrievalread) |
| `422` | `application/json` [`HTTPValidationError`](../schema-models.md#httpvalidationerror) |
