"""Render public endpoint contracts from the running FastAPI OpenAPI schema.

Run with backend dependencies installed:
  backend/.venv/bin/python docs/site/scripts/generate_api_reference.py
  backend/.venv/bin/python docs/site/scripts/generate_api_reference.py --check

Auth, workflow, costs and troubleshooting prose below is reviewed separately from
generated operation and model fields. No configuration values or credentials are read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
SITE = ROOT / "docs" / "site"
sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402

GROUPS = {
    "health": {
        "title": "Health and readiness",
        "outcome": "Distinguish a responding API process from a database and schema that can serve work.",
        "prerequisite": "Start the local backend. These two reads do not need a project ID or provider credentials.",
        "example": "curl --fail http://127.0.0.1:8000/api/health\ncurl --fail http://127.0.0.1:8000/api/ready",
        "expected": "Both return HTTP 200 with a status; readiness checks migrated database tables.",
        "failure": "If readiness returns 503, inspect the database and migration services before retrying a job.",
        "boundary": "This verifies local process/schema reachability; it does not certify provider access or shared deployment.",
        "related": "[Install locally](../../start/install.md), [API overview](../overview.md)",
    },
    "projects": {
        "title": "Projects and access",
        "outcome": "Create, list and read a project and inspect the current principal's project access.",
        "prerequisite": "Use the local loopback owner mode or a permitted OIDC token; project writes are scoped by the server.",
        "example": "curl --fail 'http://127.0.0.1:8000/api/projects?limit=20&offset=0'",
        "expected": "A paginated object with items, total, limit and offset is returned.",
        "failure": "For 401/403/404, check authentication and project membership; do not substitute another project's ID.",
        "boundary": "Local ownership is tested; live shared OIDC acceptance remains a separate release gate.",
        "related": "[Projects](../../concepts/projects.md), [API patterns](../patterns.md)",
    },
    "connections": {
        "title": "Source connections",
        "outcome": "Discover vault availability and manage opaque connection records without reading stored credentials.",
        "prerequisite": "Set PROJECT_ID to an authorized project. Connection writes require the configured encrypted vault and appropriate role.",
        "example": "curl --fail \"http://127.0.0.1:8000/api/projects/$PROJECT_ID/source-connections/settings\"",
        "expected": "The response reports safe vault availability and connection kinds, not secret values.",
        "failure": "If disabled or unavailable, configure the server-side keyring; do not put a secret in a URL or docs example.",
        "boundary": "S3, Notion and Confluence real-account permissions require separate live checks.",
        "related": "[Source connections](../../ingestion/connections.md), [Security limits](../../reference/limitations.md)",
    },
    "documents": {
        "title": "Documents and processing",
        "outcome": "Inspect upload limits, store a document and track versioned processing and canonical content.",
        "prerequisite": "Set PROJECT_ID to an authorized project; uploads use multipart form data and encrypted local artifact storage.",
        "example": "curl --fail \"http://127.0.0.1:8000/api/projects/$PROJECT_ID/upload-settings\"",
        "expected": "The response lists actual accepted formats and upload limits for this backend.",
        "failure": "For 413/422, use a supported bounded file and check the safe error. A failed run does not replace a successful processing version.",
        "boundary": "Local file processing is exercised with synthetic files; external OCR installation and protected raw reads have separate gates.",
        "related": "[Documents](../../knowledge-base/documents.md), [Prepare content](../../knowledge-base/prepare.md)",
    },
    "pipelines": {
        "title": "Saved pipelines",
        "outcome": "Inspect supported answer/ingestion options and save immutable, validated pipeline versions.",
        "prerequisite": "Set PROJECT_ID to an authorized project and have a compatible ready index or source configuration.",
        "example": "curl --fail \"http://127.0.0.1:8000/api/projects/$PROJECT_ID/pipelines/options\"",
        "expected": "The server reports configured options and availability without returning credentials.",
        "failure": "On 422, correct the graph or node setting; do not bypass server validation. Confirm a POST's result before retrying it.",
        "boundary": "Only the supported graph templates execute; arbitrary nodes or code are rejected.",
        "related": "[Answer pipelines](../../answers/pipelines.md), [Ingestion pipelines](../../ingestion/pipelines.md)",
    },
    "ingestion": {
        "title": "Ingestion previews, runs and snapshots",
        "outcome": "Inspect capabilities, preview processing, run a saved version and trace the exact source snapshot.",
        "prerequisite": "Set PROJECT_ID to an authorized project. Remote collection additionally needs a permitted source and possibly a server-side connection.",
        "example": "curl --fail \"http://127.0.0.1:8000/api/projects/$PROJECT_ID/ingestion-capabilities\"",
        "expected": "The response states installed extraction and OCR capabilities for this backend.",
        "failure": "Inspect terminal run/item states, expiry or permission errors before retrying; never treat a partial index as ready.",
        "boundary": "Synthetic local/controlled transport paths are tested; live remote accounts and paid embedding runs are not implied.",
        "related": "[Preview processing](../../ingestion/previews.md), [Run ingestion](../../ingestion/runs.md), [Source history](../../ingestion/source-history.md)",
    },
    "indexes": {
        "title": "Indexes and retrieval",
        "outcome": "List immutable index versions and retrieve passages from a compatible ready version.",
        "prerequisite": "Set PROJECT_ID to an authorized project and publish a ready index.",
        "example": "curl --fail \"http://127.0.0.1:8000/api/projects/$PROJECT_ID/indexes?limit=20&offset=0\"",
        "expected": "A paginated list includes index status, version and source membership metadata.",
        "failure": "If retrieval returns 409, select a ready compatible index; do not query a partial or incompatible one.",
        "boundary": "PostgreSQL/pgvector retrieval is locally tested; relevance and model cost depend on the configured provider and corpus.",
        "related": "[Collections](../../knowledge-base/collections.md), [Retrieval settings](../../answers/retrieval.md)",
    },
    "queries": {
        "title": "Answer query runs",
        "outcome": "List persisted answer runs and inspect the exact version, evidence and status of a question.",
        "prerequisite": "Set PROJECT_ID to an authorized project; a submitted question needs a ready index and answer provider.",
        "example": "curl --fail \"http://127.0.0.1:8000/api/projects/$PROJECT_ID/query-runs?limit=20&offset=0\"",
        "expected": "The response contains paginated saved runs, including failed or insufficient-evidence states.",
        "failure": "If execution fails, inspect the safe error and submit a new question after correction; this path has no cancellation endpoint.",
        "boundary": "Answer generation can incur provider charges; unknown dollar cost is not zero.",
        "related": "[Playground](../../answers/playground.md), [Past questions](../../answers/history.md)",
    },
    "evaluation": {
        "title": "Datasets and experiments",
        "outcome": "Import a reviewed dataset, submit a versioned comparison and inspect each result and aggregate.",
        "prerequisite": "Set PROJECT_ID to an authorized project; evaluator execution needs saved answer versions and configured server-side providers.",
        "example": "curl --fail \"http://127.0.0.1:8000/api/projects/$PROJECT_ID/datasets/example.csv\"",
        "expected": "A UTF-8 CSV example with the current accepted headers is returned.",
        "failure": "For 409 after import, preview the same file again; for failed experiment items, inspect reasons before scheduling another paid run.",
        "boundary": "Deterministic local orchestration is tested; live RAGAS judgments and paid evaluator costs need separate authorization.",
        "related": "[Datasets](../../experiments/datasets.md), [Run experiments](../../experiments/runs.md), [Metrics](../../experiments/metrics.md)",
    },
}

METHODS = {"get", "post", "put", "patch", "delete"}


def group_for(path: str) -> str:
    if path in ("/api/health", "/api/ready"):
        return "health"
    tail = path.removeprefix("/api/projects")
    if tail in ("", "/{project_id}", "/{project_id}/access"):
        return "projects"
    if "/source-connections" in tail:
        return "connections"
    if "/datasets" in tail or "/experiments" in tail:
        return "evaluation"
    if any(part in tail for part in ("/documents", "/processing-runs", "/content-derivations", "/upload-settings")):
        return "documents"
    if any(part in tail for part in ("/ingestion-", "/source-previews", "/source-snapshots", "/ingestion-schedules")):
        return "ingestion"
    if "/pipelines" in tail:
        return "pipelines"
    if any(part in tail for part in ("/indexes", "/knowledge-sets", "/retrieval", "/embedding-settings")):
        return "indexes"
    if "/query-runs" in tail:
        return "queries"
    raise ValueError(f"Unclassified OpenAPI path: {path}")


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip() or "—"


def schema_type(value: dict) -> str:
    if "$ref" in value:
        return f"[`{value['$ref'].split('/')[-1]}`](../schema-models.md#{value['$ref'].split('/')[-1].lower()})"
    if "anyOf" in value:
        return " or ".join(schema_type(x) for x in value["anyOf"])
    if "oneOf" in value:
        return " or ".join(schema_type(x) for x in value["oneOf"])
    if "allOf" in value:
        return " and ".join(schema_type(x) for x in value["allOf"])
    kind = value.get("type") or "object"
    if kind == "array":
        return f"array of {schema_type(value.get('items', {}))}"
    if "enum" in value:
        return f"{kind}: {', '.join(map(str, value['enum']))}"
    return f"{kind}{' (' + value['format'] + ')' if value.get('format') else ''}"


def constraints(value: dict) -> str:
    parts = []
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "pattern", "default"):
        if key in value:
            parts.append(f"{key}={value[key]}")
    return ", ".join(parts) or "—"


def media_rows(content: dict) -> str:
    if not content:
        return "—"
    return "; ".join(f"`{media}` {schema_type(spec.get('schema', {}))}" for media, spec in sorted(content.items()))


def generate_group(key: str, operations: list[tuple[str, str, dict]], digest: str) -> str:
    info = GROUPS[key]
    result = [
        "---",
        f'verified_against: "OpenAPI SHA-256 {digest} (2026-09-26)"',
        f"title: {info['title']}",
        f"slug: /api/reference/{key}/",
        "---",
        "",
        info["outcome"],
        "",
        f"**Prerequisite:** {info['prerequisite']} For project-scoped examples, set `PROJECT_ID` to the ID returned by [creating a local project](../patterns.md); do not use another project's ID.",
        "",
        "```sh",
        info["example"],
        "```",
        "",
        f"**Expected result:** {info['expected']} **If it fails:** {info['failure']}",
        "",
        f"**Capability boundary:** {info['boundary']} Related: {info['related']}. The operation table below is generated from the [validated schema](/openapi.json); it does not replace the task guide.",
        "",
        "## Operations",
        "",
    ]
    for method, path, operation in operations:
        result.extend([f"### {method.upper()} `{path}`", ""])
        result.append(f"OpenAPI operation ID: `{operation.get('operationId', 'not supplied')}`.")
        result.append("")
        params = operation.get("parameters", [])
        if params:
            result.extend(["| Parameter | In | Required | Type | Bounds/default |", "| --- | --- | --- | --- | --- |"])
            for param in params:
                spec = param.get("schema", {})
                result.append(f"| `{cell(param['name'])}` | {cell(param['in'])} | {'yes' if param.get('required') else 'no'} | {schema_type(spec)} | {cell(constraints(spec))} |")
            result.append("")
        body = operation.get("requestBody")
        result.append(f"**Request body:** {media_rows(body.get('content', {})) if body else 'none'}." + (" Required." if body and body.get("required") else ""))
        result.extend(["", "| Response | Content contract |", "| --- | --- |"])
        for status, response in sorted(operation.get("responses", {}).items()):
            result.append(f"| `{status}` | {cell(media_rows(response.get('content', {})))} |")
        result.append("")
    return "\n".join(result)


def generate_models(components: dict, digest: str) -> str:
    result = [
        "---",
        f'verified_against: "OpenAPI SHA-256 {digest} (2026-09-26)"',
        "title: Schema models",
        "slug: /api/schema-models/",
        "---",
        "",
        "Inspect generated model fields and bounds before submitting a request. Start the [local API](../start/install.md), then use `curl --fail http://127.0.0.1:8000/openapi.json -o /tmp/rag-quality-studio-openapi.json` to compare the running contract with this [checked schema](/openapi.json). Expected result: the same component names and constraints. If the server differs, use its live schema and review the application version before sending a write.",
        "",
        "This page is generated from FastAPI/Pydantic; project authorization, provider cost and workflow order need the [API overview](./overview.md), [patterns](./patterns.md), and [task guides](../start/index.md). A schema field does not imply a live external integration has been verified.",
        "",
    ]
    for name, schema in sorted(components.items()):
        result.extend([f"## {name}", ""])
        if schema.get("description"):
            result.extend([cell(schema["description"]), ""])
        if schema.get("properties"):
            required = set(schema.get("required", []))
            result.extend(["| Field | Type | Required | Bounds/default |", "| --- | --- | --- | --- |"])
            for prop, spec in schema["properties"].items():
                result.append(f"| `{cell(prop)}` | {schema_type(spec).replace('../schema-models.md#', '#')} | {'yes' if prop in required else 'no'} | {cell(constraints(spec))} |")
        else:
            result.append(f"Type: {schema_type(schema).replace('../schema-models.md#', '#')}.")
        result.append("")
    return "\n".join(result)


def main() -> None:
    import hashlib

    schema = app.openapi()
    assert schema.get("openapi") and schema.get("paths") and schema.get("components", {}).get("schemas")
    components = schema["components"]["schemas"]

    def verify_refs(value: object) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                if not ref.startswith("#/components/schemas/") or ref.split("/")[-1] not in components:
                    raise ValueError(f"Broken schema reference: {ref}")
            for child in value.values():
                verify_refs(child)
        elif isinstance(value, list):
            for child in value:
                verify_refs(child)

    verify_refs(schema)
    raw = json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    grouped = {key: [] for key in GROUPS}
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in METHODS:
                grouped[group_for(path)].append((method, path, operation))
    if any(not operations for operations in grouped.values()):
        raise ValueError("Every endpoint group must contain an operation")
    output = {SITE / "static" / "openapi.json": raw}
    target = SITE / "docs" / "api" / "reference"
    for key, operations in grouped.items():
        output[target / f"{key}.md"] = generate_group(key, operations, digest)
    output[SITE / "docs" / "api" / "schema-models.md"] = generate_models(components, digest)
    check = "--check" in sys.argv
    for path, content in output.items():
        if check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Generated API reference differs from app.openapi(): {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    print(f"{'Checked' if check else 'Generated'} {sum(map(len, grouped.values()))} operations, {len(components)} schemas, {len(output)} artifacts; SHA-256 {digest[:12]}")


if __name__ == "__main__":
    main()
