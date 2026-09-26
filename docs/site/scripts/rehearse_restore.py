"""Seed or verify an isolated encrypted-artifact restore using test providers only.

This script refuses an ordinary backend: the test-only /api/test/* routes must
exist. It does not create, stop, back up, restore, or delete Docker resources.
Use separate Compose projects and keep the record outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs/site/static/examples/orchard.txt"


def request(
    api: str,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    form: str | None = None,
):
    command = ["curl", "--fail-with-body", "--max-time", "30", "-sS", "-X", method]
    if body is not None:
        command += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    if form is not None:
        command += ["-F", form]
    command.append(api + path)
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def wait_for(api: str, path: str) -> dict:
    for _ in range(60):
        value = request(api, "GET", path)
        if value["status"] == "succeeded":
            return value
        if value["status"] in {"failed", "cancelled"}:
            raise AssertionError(
                f"{path} ended {value['status']}: {value.get('error')}"
            )
        time.sleep(2)
    raise AssertionError(f"{path} did not complete within 120 seconds")


def require_fixture_backend(api: str) -> None:
    parsed = urlsplit(api)
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("Restore rehearsal requires a loopback HTTP test API")
    schema = request(api, "GET", "/openapi.json")
    assert "/api/test/s3-state/{state}" in schema["paths"], (
        "Refusing a non-fixture backend"
    )
    assert request(api, "GET", "/api/ready")["status"] == "ready"


def seed(api: str, record: Path) -> None:
    if record.exists():
        raise FileExistsError(f"Refusing to overwrite restore record: {record}")
    project = request(
        api, "POST", "/api/projects", body={"name": "Docs restore rehearsal"}
    )
    base = f"/api/projects/{project['id']}"
    document = request(
        api, "POST", base + "/documents", form=f"file=@{SOURCE};type=text/plain"
    )
    doc_base = base + f"/documents/{document['id']}"
    processing = request(
        api, "POST", doc_base + "/runs", body={"chunk_size": 1000, "overlap": 100}
    )
    wait_for(api, doc_base + f"/runs/{processing['id']}")
    index = request(api, "POST", base + "/indexes", body={})
    wait_for(api, base + f"/indexes/{index['id']}")
    query = request(
        api,
        "POST",
        base + "/query-runs",
        body={"index_id": index["id"], "question": "What does the orchard grow?"},
    )
    assert query["status"] == "succeeded" and query["snapshot"]["evidence"]
    rewrap = request(api, "POST", doc_base + "/artifact/rewrap")
    assert rewrap["key_version"] == "rehearsal-v1", rewrap
    record_json = (
        json.dumps(
            {
                "project_id": project["id"],
                "document_id": document["id"],
                "processing_id": processing["id"],
                "index_id": index["id"],
                "query_id": query["id"],
                "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    descriptor = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(record_json)
    print("Seeded one encrypted synthetic artifact, ready index and cited query.")


def verify(api: str, record: Path) -> None:
    saved = json.loads(record.read_text())
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == saved["source_sha256"]
    base = f"/api/projects/{saved['project_id']}"
    assert request(api, "GET", base)["id"] == saved["project_id"]
    documents = request(api, "GET", base + "/documents?limit=20&offset=0")
    assert any(value["id"] == saved["document_id"] for value in documents["items"])
    index = request(api, "GET", base + f"/indexes/{saved['index_id']}")
    assert index["status"] == "succeeded"
    old_query = request(api, "GET", base + f"/query-runs/{saved['query_id']}")
    assert old_query["status"] == "succeeded" and old_query["snapshot"]["evidence"]
    doc_base = base + f"/documents/{saved['document_id']}"
    rewrap = request(api, "POST", doc_base + "/artifact/rewrap")
    assert rewrap["key_version"] == "rehearsal-v1", rewrap
    new_run = request(
        api, "POST", doc_base + "/runs", body={"chunk_size": 1000, "overlap": 100}
    )
    wait_for(api, doc_base + f"/runs/{new_run['id']}")
    chunks = request(api, "GET", doc_base + f"/runs/{new_run['id']}/chunks")
    assert chunks["total"] > 0
    assert (
        request(api, "GET", base + f"/indexes/{saved['index_id']}")["status"]
        == "succeeded"
    )
    print(
        "Restored project, historical evidence, ready index and decryptable raw artifact verified."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["seed", "verify"])
    parser.add_argument(
        "--api", required=True, help="Loopback URL of an isolated test-provider API"
    )
    parser.add_argument(
        "--record", required=True, type=Path, help="Record file outside the repository"
    )
    args = parser.parse_args()
    require_fixture_backend(args.api)
    (seed if args.mode == "seed" else verify)(args.api.rstrip("/"), args.record)


if __name__ == "__main__":
    main()
