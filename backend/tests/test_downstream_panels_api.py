"""Spec 0012 Slice 4: the numbers the Chunk, Embed and Publish panels show."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.workers.previews import process_preview
from test_documents import documents_api, upload  # noqa: F401
from test_existing_files_ingestion import (  # noqa: F401
    ingestion_api,
    ingestion_draft,
)
from test_publish_destinations import _run_to_completion

TEXT = b"Lanterns light the archive. Maps cover the harbour hall. " * 30


@pytest.fixture
def api(ingestion_api):  # noqa: F811
    return ingestion_api


def test_a_preview_summarizes_passages_and_what_a_run_would_embed(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "summary.txt")
    payload = ingestion_draft(
        [document["id"]], config, name="Summary", schema_version=2
    )
    accepted = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    )
    assert accepted.status_code == 202, accepted.text
    preview_id = accepted.json()["id"]
    process_preview(UUID(preview_id), engine)
    preview = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}"
    ).json()
    item = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}/items"
    ).json()["items"][0]
    summary = item["metrics"]["chunk_summary"]
    assert summary["count"] == item["metrics"]["chunk_count"] > 0
    assert (
        summary["minimum_bytes"] <= summary["median_bytes"] <= summary["maximum_bytes"]
    )
    assert summary["over_embed_limit"] == 0
    assert preview["cost_basis"]["embedding_estimate"] == {
        "chunks": summary["count"],
        "embedding_bytes": summary["embedding_bytes"],
    }


def test_a_second_version_reports_its_reused_vectors(api):
    client, engine, project_id, _, config, provider = api
    document = upload(client, project_id, TEXT, "reuse.txt")
    payload = ingestion_draft([document["id"]], config, name="Reuse", schema_version=2)
    first = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    run = _run_to_completion(client, engine, project_id, first)
    assert run["embedding_usage"]["reused_vectors"] == 0
    calls = len(provider.calls)

    # The second version adds a file, so it publishes (an unchanged run would
    # publish nothing, spec 0012 D8).
    added = upload(client, project_id, b"Tides turn at the harbour. " * 20, "add.txt")
    payload = ingestion_draft(
        [document["id"], added["id"]], config, name="Reuse", schema_version=2
    )
    second = client.post(
        f"/api/projects/{project_id}/pipelines/{first['pipeline_id']}/versions",
        json=payload,
    ).json()
    again = _run_to_completion(client, engine, project_id, second)
    # The first file's text and model are unchanged: its vectors are copied and
    # only the added file's passages are requested.
    assert len(provider.calls) > calls
    assert again["embedding_usage"]["reused_vectors"] == run["chunk_count"] > 0
    assert again["embedded_count"] > run["chunk_count"]
