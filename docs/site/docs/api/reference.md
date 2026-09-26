---
verified_against: "481b4eca90c5 + docs phase 3 generated OpenAPI (2026-09-26)"
title: Endpoint reference
slug: /api/reference/
---

Find the current path, method, parameters, request media type, success response and schema fields for an integration. Start the [local API](../start/install.md), then check `curl --fail http://127.0.0.1:8000/openapi.json -o /tmp/rag-quality-studio-openapi.json`. The checked [machine-readable schema](/openapi.json) and the operation pages below are generated from the canonical `app.openapi()` and checked for drift with `backend/.venv/bin/python docs/site/scripts/generate_api_reference.py --check`. The isolated test transport registers three extra `/api/test/` routes; they are deliberately excluded from this public contract.

| Group | First safe request | Task guide |
| --- | --- | --- |
| [Health and readiness](./reference/health.md) | `GET /api/health` | [Install](../start/install.md) |
| [Projects and access](./reference/projects.md) | `GET /api/projects` | [Projects](../concepts/projects.md) |
| [Source connections](./reference/connections.md) | `GET /api/projects/{project_id}/source-connections/settings` | [Connections](../ingestion/connections.md) |
| [Documents and processing](./reference/documents.md) | `GET /api/projects/{project_id}/upload-settings` | [Documents](../knowledge-base/documents.md) |
| [Saved pipelines](./reference/pipelines.md) | `GET /api/projects/{project_id}/pipelines/options` | [Answer pipelines](../answers/pipelines.md) |
| [Ingestion previews, runs and snapshots](./reference/ingestion.md) | `GET /api/projects/{project_id}/ingestion-capabilities` | [Ingestion runs](../ingestion/runs.md) |
| [Indexes and retrieval](./reference/indexes.md) | `GET /api/projects/{project_id}/indexes` | [Retrieval](../answers/retrieval.md) |
| [Answer query runs](./reference/queries.md) | `GET /api/projects/{project_id}/query-runs` | [Past questions](../answers/history.md) |
| [Datasets and experiments](./reference/evaluation.md) | `GET /api/projects/{project_id}/datasets/example.csv` | [Experiments](../experiments/runs.md) |

[Schema models](./schema-models.md) list Pydantic field types and bounds. A 200 contract without a response model is labeled as such in the generated pages; inspect the actual task guide or running API before depending on undocumented fields. OpenAPI cannot express every server-side access, compatibility or cost rule. In local mode loopback requests use one owner; OIDC Bearer requests require project membership and have not passed shared deployment acceptance. See [authentication](./overview.md), [errors and versioned jobs](./patterns.md), [cost/metric boundaries](../experiments/metrics.md), and [workflow recipes](./recipes.md).

Expected result: each group has a reachable route and all listed schema references resolve. If a path or field differs from the running server, check the app version and regenerate/review the reference; do not send a write based on a stale page. The generated files document contracts, while live external providers and paid work remain separate gates.
