"""Run public API read examples and the synthetic upload/query recipe on E2E only.

Requires the isolated rag-docs-e2e stack with test-only provider transport at
http://127.0.0.1:8002. Refuses a backend without its private fixture routes.
Does not reset or delete project data.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

API = "http://127.0.0.1:8002"
ROOT = Path(__file__).resolve().parents[3]


def call(method: str, path: str, *, body: dict | None = None, form: list[str] | None = None):
    command = ["curl", "--fail-with-body", "--max-time", "30", "-sS", "-X", method]
    if body is not None:
        command += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    for field in form or []:
        command += ["-F", field]
    command.append(API + path)
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def terminal(path: str, label: str) -> dict:
    for _ in range(60):
        value = call("GET", path)
        if value["status"] == "succeeded":
            return value
        if value["status"] in {"failed", "cancelled"}:
            raise AssertionError(f"{label} ended {value['status']}: {value.get('error')}")
        time.sleep(2)
    raise AssertionError(f"{label} did not complete within 120 seconds")


def main() -> None:
    spec = call("GET", "/openapi.json")
    assert "/api/test/s3-state/{state}" in spec["paths"], "Refusing a non-fixture backend"
    assert call("GET", "/api/health")["status"] == "ok"
    assert call("GET", "/api/ready")["status"] == "ready"
    project = call("POST", "/api/projects", body={"name": "Docs API recipe fixture"})
    project_id = project["id"]
    base = f"/api/projects/{project_id}"
    assert call("GET", "/api/projects?limit=20&offset=0")["total"] >= 1
    for path in (
        "/source-connections/settings",
        "/upload-settings",
        "/pipelines/options",
        "/ingestion-capabilities",
        "/indexes?limit=20&offset=0",
        "/query-runs?limit=20&offset=0",
    ):
        assert call("GET", base + path) is not None
    assert "question,reference_answer" in call("GET", base + "/datasets/example.csv")

    source = ROOT / "docs/site/static/examples/orchard.txt"
    document = call(
        "POST", base + "/documents", form=[f"file=@{source};type=text/plain"]
    )
    run = call(
        "POST",
        base + f"/documents/{document['id']}/runs",
        body={"chunk_size": 1000, "overlap": 100},
    )
    terminal(base + f"/documents/{document['id']}/runs/{run['id']}", "processing")
    index = call("POST", base + "/indexes", body={})
    terminal(base + f"/indexes/{index['id']}", "index")
    answer = call(
        "POST",
        base + "/query-runs",
        body={"index_id": index["id"], "question": "What does the orchard grow?"},
    )
    assert answer["status"] == "succeeded"
    assert answer["snapshot"]["evidence"]
    assert call("GET", base + f"/query-runs/{answer['id']}")["id"] == answer["id"]

    csv_path = ROOT / "docs/site/static/examples/orchard-reviewed.csv"
    form = [f"file=@{csv_path};type=text/csv"]
    preview = call("POST", base + "/datasets/preview", form=form)
    assert len(preview["rows"]) == 2 and not preview["errors"]
    dataset = call(
        "POST",
        base + "/datasets",
        form=form + ["name=Reviewed orchard", f"content_hash={preview['content_hash']}"],
    )
    assert dataset["version"] == 1
    print(
        "Verified 9 endpoint-group read examples and synthetic project → upload → processing → ready index → cited query → dataset import on isolated PostgreSQL/pgvector."
    )


if __name__ == "__main__":
    main()
