"""Spec 0012 Slice 1: where a pipeline publishes (D2, D3) and what a run reports."""

from __future__ import annotations

from uuid import UUID

import pytest

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.index import IndexVersion
from app.models.ingestion import IngestionRun
from test_documents import documents_api, upload  # noqa: F401
from test_existing_files_ingestion import (  # noqa: F401
    embed_until_ready,
    ingestion_api,
    ingestion_draft,
)
from app.workers.ingestion import process_ingestion
from app.workers.processing import process
from app.models.ingestion import IngestionRunItem


@pytest.fixture
def api(ingestion_api):  # noqa: F811
    return ingestion_api


TEXT = b"Lanterns light the archive. " * 20


def _publish(version):
    return next(
        node
        for node in version["execution"]["nodes"]
        if node["type"] == "publish_index"
    )


def _run_to_completion(client, engine, project_id, version):
    response = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["id"])
    with Session(engine) as session:
        processing = session.scalars(
            select(IngestionRunItem.processing_run_id).where(
                IngestionRunItem.run_id == run_id
            )
        ).all()
    for processing_id in processing:
        process(processing_id, engine)
    process_ingestion(run_id, engine)
    with Session(engine) as session:
        index_id = session.scalar(
            select(IndexVersion.id).where(IndexVersion.ingestion_run_id == run_id)
        )
    embed_until_ready(engine, index_id)
    process_ingestion(run_id, engine)
    return client.get(f"/api/projects/{project_id}/ingestion-runs/{run_id}").json()


def test_a_pipeline_publishes_to_its_own_new_index_and_reuses_it(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "own.txt")
    payload = ingestion_draft([document["id"]], config, name="Own", schema_version=2)
    first = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    assert _publish(first) == {
        "id": "publish",
        "type": "publish_index",
        "knowledge_set_name": "Own",
        "knowledge_set_id": None,
        "destination": "new",
    }
    run = _run_to_completion(client, engine, project_id, first)
    assert run["status"] == "succeeded"
    assert run["published_index_version"] == 1
    assert run["prior_index_version"] is None and run["is_current"] is True

    # A second version of the same pipeline adds a version to the index its
    # first run created, explicitly. It adds a file: an unchanged run would
    # publish nothing (spec 0012 D8).
    extra = upload(client, project_id, b"Tides turn at the harbour. " * 20, "own2.txt")
    payload = ingestion_draft(
        [document["id"], extra["id"]], config, name="Own", schema_version=2
    )
    second = client.post(
        f"/api/projects/{project_id}/pipelines/{first['pipeline_id']}/versions",
        json=payload,
    )
    assert second.status_code == 201, second.text
    publish = _publish(second.json())
    assert publish["destination"] == "existing"
    assert publish["knowledge_set_id"] == run["knowledge_set_id"]
    again = _run_to_completion(client, engine, project_id, second.json())
    assert again["knowledge_set_id"] == run["knowledge_set_id"]
    assert again["published_index_version"] == 2
    assert again["prior_index_version"] == 1 and again["is_current"] is True
    previous = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}"
    ).json()
    assert previous["is_current"] is False

    sets = client.get(f"/api/projects/{project_id}/knowledge-sets").json()["items"]
    own = next(item for item in sets if item["id"] == run["knowledge_set_id"])
    assert own["current_version"] == 2 and own["latest_version"] == 2
    assert own["publishing_pipelines"] == [{"id": first["pipeline_id"], "name": "Own"}]


def test_two_new_pipelines_cannot_share_a_name_even_before_either_runs(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "pair.txt")
    payload = ingestion_draft([document["id"]], config, name="Shared", schema_version=2)
    first = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    second = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    _run_to_completion(client, engine, project_id, first)

    # The second was saved as a new index before the first run took the name.
    response = client.post(
        f"/api/projects/{project_id}/pipelines/{second['pipeline_id']}"
        f"/versions/{second['id']}/ingestion-runs"
    )
    assert response.status_code == 409
    assert 'An index named "Shared" already exists.' in response.json()["detail"]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(IngestionRun.id).where(
                    IngestionRun.pipeline_version_id == UUID(second["id"])
                )
            )
            is None
        )


def test_adding_a_version_to_an_existing_index_by_id(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "add.txt")
    payload = ingestion_draft([document["id"]], config, name="Base", schema_version=2)
    base = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    run = _run_to_completion(client, engine, project_id, base)

    # Another file, so the run adds a version rather than finding no change.
    extra = upload(client, project_id, b"Tides turn at the harbour. " * 20, "add2.txt")
    other = ingestion_draft(
        [document["id"], extra["id"]], config, name="Nightly", schema_version=2
    )
    publish = next(
        n for n in other["execution"]["nodes"] if n["type"] == "publish_index"
    )
    publish.update(
        knowledge_set_id=run["knowledge_set_id"],
        knowledge_set_name="Base",
        destination="existing",
    )
    saved = client.post(f"/api/projects/{project_id}/pipelines", json=other)
    assert saved.status_code == 201, saved.text
    result = _run_to_completion(client, engine, project_id, saved.json())
    assert result["knowledge_set_id"] == run["knowledge_set_id"]
    assert result["published_index_version"] == 2

    sets = client.get(f"/api/projects/{project_id}/knowledge-sets").json()["items"]
    shared = next(item for item in sets if item["id"] == run["knowledge_set_id"])
    assert [p["name"] for p in shared["publishing_pipelines"]] == ["Base", "Nightly"]


def test_inconsistent_destination_choices_are_rejected(api):
    client, _, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "bad.txt")
    payload = ingestion_draft([document["id"]], config, name="Bad", schema_version=2)
    publish = next(
        n for n in payload["execution"]["nodes"] if n["type"] == "publish_index"
    )
    publish["destination"] = "existing"
    response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert response.status_code == 422
    assert "Choose the index to add a version to." in response.text
