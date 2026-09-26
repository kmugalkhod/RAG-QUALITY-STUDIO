---
verified_against: "481b4eca90c5 + docs phase 3 working tree (2026-09-26)"
title: API workflow recipes
slug: /api/recipes/
---

Create a fictional project, upload and process one file, publish a ready index, and ask a cited question without losing any version IDs. The commands below assume the repository root, a local backend at `127.0.0.1:8000`, `python3`, `curl`, a running worker and server-side model configuration. Run them against an isolated project. The processing and indexing steps can incur embedding cost; the answer step can incur generation cost. No credentials belong in the script or browser.

![The API returns a project ID, document ID, processing run ID and ready index ID in sequence; poll both jobs before querying that index](/img/api-workflow.svg)

<a href="/img/api-workflow.svg">Open the API workflow diagram at full size</a>. In text: create a project and upload, poll the processing run to success, publish and poll the index to success, then query using that exact ready index ID. A 202 response only confirms a job was accepted.

## Upload → process → index → query

```sh
API_BASE=http://127.0.0.1:8000
PROJECT_ID=$(curl --fail-with-body --max-time 15 -sS -H 'Content-Type: application/json' \
  -d '{"name":"Orchard API recipe"}' "$API_BASE/api/projects" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
DOCUMENT_ID=$(curl --fail-with-body --max-time 15 -sS \
  -F 'file=@docs/site/static/examples/orchard.txt;type=text/plain' \
  "$API_BASE/api/projects/$PROJECT_ID/documents" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
RUN_ID=$(curl --fail-with-body --max-time 15 -sS -H 'Content-Type: application/json' \
  -d '{"chunk_size":1000,"overlap":100}' \
  "$API_BASE/api/projects/$PROJECT_ID/documents/$DOCUMENT_ID/runs" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
```

`POST /documents` returns 201 and a document ID. `POST /runs` returns 202 and a processing run ID; it does not mean chunks are ready yet. Poll the exact run, bounded to two minutes:

```sh
for attempt in $(seq 1 60); do
  RUN_STATUS=$(curl --fail-with-body --max-time 15 -sS \
    "$API_BASE/api/projects/$PROJECT_ID/documents/$DOCUMENT_ID/runs/$RUN_ID" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$RUN_STATUS" in
    succeeded) break ;;
    failed|cancelled) echo "Processing ended: $RUN_STATUS" >&2; exit 1 ;;
  esac
  sleep 2
done
test "$RUN_STATUS" = succeeded || { echo 'Processing timed out; inspect the saved run' >&2; exit 1; }
INDEX_ID=$(curl --fail-with-body --max-time 15 -sS -H 'Content-Type: application/json' \
  -d '{}' "$API_BASE/api/projects/$PROJECT_ID/indexes" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
for attempt in $(seq 1 60); do
  INDEX_STATUS=$(curl --fail-with-body --max-time 15 -sS \
    "$API_BASE/api/projects/$PROJECT_ID/indexes/$INDEX_ID" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$INDEX_STATUS" in
    succeeded) break ;;
    failed|cancelled) echo "Index ended: $INDEX_STATUS" >&2; exit 1 ;;
  esac
  sleep 2
done
test "$INDEX_STATUS" = succeeded || { echo 'Index timed out; inspect the saved index' >&2; exit 1; }
curl --fail-with-body --max-time 60 -sS -H 'Content-Type: application/json' \
  -d "{\"index_id\":\"$INDEX_ID\",\"question\":\"What does the orchard grow?\"}" \
  "$API_BASE/api/projects/$PROJECT_ID/query-runs"
```

Expected result: processing and index GETs reach `succeeded`; the query returns a persisted result with its index version and evidence in `snapshot`. An insufficient-evidence response is a valid terminal outcome when the source does not answer the question. The run IDs allow you to inspect failures without repeating paid calls. If a POST times out after acceptance, fetch/list the matching resource before retrying: these POSTs are not a general idempotent replay API. A 409 on query means the index is not ready; a 422 identifies a malformed body or bounds. See [endpoint contracts](./reference.md), [version provenance](../concepts/versions.md), and [evidence inspection](../answers/evidence.md).

## Reviewed dataset → experiment

After you save one or two answer versions with the same index, record their exact `version_id` values from `GET /api/projects/$PROJECT_ID/pipelines/$PIPELINE_ID/versions`. Preview the fictional CSV first; import uses the exact preview hash:

```sh
CSV_HASH=$(curl --fail-with-body --max-time 15 -sS \
  -F 'file=@docs/site/static/examples/orchard-reviewed.csv;type=text/csv' \
  "$API_BASE/api/projects/$PROJECT_ID/datasets/preview" |
  python3 -c 'import json,sys; value=json.load(sys.stdin); assert not value["errors"]; print(value["content_hash"])')
DATASET_VERSION_ID=$(curl --fail-with-body --max-time 15 -sS \
  -F 'file=@docs/site/static/examples/orchard-reviewed.csv;type=text/csv' \
  -F 'name=Reviewed orchard' -F "content_hash=$CSV_HASH" \
  "$API_BASE/api/projects/$PROJECT_ID/datasets" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
```

Submit only after checking evaluator availability with `GET /api/projects/$PROJECT_ID/experiments/options`. `POST /experiments` accepts `dataset_version_id`, one or two distinct `pipeline_version_ids`, and selected `metrics`, then returns 202 with a run ID. For example, use the saved version ID you actually read:

```sh
test -n "$PIPELINE_VERSION_ID" || { echo 'Set a saved PIPELINE_VERSION_ID first' >&2; exit 1; }
curl --fail-with-body --max-time 15 -sS -H 'Content-Type: application/json' \
  -d "{\"name\":\"Orchard API evaluation\",\"dataset_version_id\":\"$DATASET_VERSION_ID\",\"pipeline_version_ids\":[\"$PIPELINE_VERSION_ID\"],\"metrics\":[\"faithfulness\",\"context_recall\"]}" \
  "$API_BASE/api/projects/$PROJECT_ID/experiments"
```

Poll the returned `/experiments/{experiment_id}` until `succeeded`, `failed` or `cancelled`, then inspect `items` and `summary`; `GET /experiments/{experiment_id}/export.csv` retains row statuses and lineage. Missing references make context recall unavailable, never zero. Do not blindly resubmit after a network timeout, because evaluator work can be billed even when a later step fails. The deterministic local T4 path is [documented here](../experiments/compare.md); live RAGAS scoring remains unverified.

## Reuse a remote snapshot

After a successful remote collection, list `/source-snapshots`, select the exact snapshot ID and a compatible saved ingestion `pipeline_id` and `version_id`, then submit a new destination:

```json
{
  "source_input": {"kind": "snapshot", "source_snapshot_id": "<saved snapshot UUID>"},
  "destination": {"kind": "new", "name": "Second index from saved source"}
}
```

Send this body to `POST /api/projects/{project_id}/pipelines/{pipeline_id}/versions/{version_id}/ingestion-runs`. Expected result: 202 and a run that reads retained revisions without a new remote fetch. Snapshot compatibility, permission, artifact retention and embedding checks remain server authoritative; `410` or a terminal failure is not permission to silently refetch and call it the same snapshot. This recipe was exercised with controlled Website transport only; a real remote account or host requires its own authorized gate. See [source history](../ingestion/source-history.md) and [ingestion runs](../ingestion/runs.md).

These commands describe local owner mode. In shared OIDC mode, a permitted client must add a bearer header and project membership; shared deployment has not been live-verified. Unknown model prices are not zero, and no paid call was made to verify these published examples.
