"""Spec 0012 D8: a refresh with no change publishes no new index version."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun, IngestionRunItem, IngestionRunNode
from app.services import indexes
from app.workers.ingestion import process_ingestion
from app.workers.processing import process
from test_documents import documents_api, upload  # noqa: F401
from test_existing_files_ingestion import (  # noqa: F401
    embed_until_ready,
    ingestion_api,
    ingestion_draft,
)


@pytest.fixture
def api(ingestion_api):  # noqa: F811
    return ingestion_api


TEXT = b"Lanterns light the archive at dusk. " * 30


def _run(client, engine, project_id, version):
    response = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["id"])
    with Session(engine) as session:
        processing = session.scalars(
            select(IngestionRunItem.processing_run_id).where(
                IngestionRunItem.run_id == run_id,
                IngestionRunItem.processing_created.is_(True),
            )
        ).all()
    for processing_id in processing:
        process(processing_id, engine)
    process_ingestion(run_id, engine)
    with Session(engine) as session:
        index_id = session.scalar(
            select(IndexVersion.id).where(IndexVersion.ingestion_run_id == run_id)
        )
    if index_id is not None:
        embed_until_ready(engine, index_id)
        process_ingestion(run_id, engine)
    return client.get(f"/api/projects/{project_id}/ingestion-runs/{run_id}").json()


def _versions(engine, knowledge_set_id):
    with Session(engine) as session:
        return session.scalar(
            select(func.count())
            .select_from(IndexVersion)
            .where(IndexVersion.knowledge_set_id == UUID(knowledge_set_id))
        )


def test_an_unchanged_refresh_publishes_nothing_and_keeps_the_version(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "lanterns.txt")
    payload = ingestion_draft(
        [document["id"]], config, name="Lanterns", schema_version=2
    )
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()

    first = _run(client, engine, project_id, version)
    assert first["status"] == "succeeded"
    assert first["published_index_version"] == 1

    again = _run(client, engine, project_id, version)
    assert again["status"] == "succeeded"
    assert again["published_index_id"] is None
    assert again["published_index_version"] is None
    assert again["published_count"] == 0
    assert again["unchanged_index_id"] == first["published_index_id"]
    assert again["unchanged_index_version"] == 1
    assert again["is_current"] is True
    assert again["embedding_usage"] is None
    assert again["chunk_count"] == first["chunk_count"]
    assert {state["status"] for state in again["node_states"]} == {"succeeded"}
    assert _versions(engine, first["knowledge_set_id"]) == 1
    sets = client.get(f"/api/projects/{project_id}/knowledge-sets").json()["items"]
    own = next(item for item in sets if item["id"] == first["knowledge_set_id"])
    assert own["current_version"] == 1 and own["latest_version"] == 1
    # The first run's index is still the current one.
    first = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{first['id']}"
    ).json()
    assert first["is_current"] is True


def test_a_changed_source_still_publishes(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "first.txt")
    payload = ingestion_draft(
        [document["id"]], config, name="Growing", schema_version=2
    )
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    first = _run(client, engine, project_id, version)
    assert first["published_index_version"] == 1

    added = upload(
        client, project_id, b"A second file about tides. " * 30, "second.txt"
    )
    payload = ingestion_draft(
        [document["id"], added["id"]], config, name="Growing", schema_version=2
    )
    changed = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}/versions",
        json=payload,
    )
    assert changed.status_code == 201, changed.text
    second = _run(client, engine, project_id, changed.json())
    assert second["status"] == "succeeded"
    assert second["published_index_version"] == 2
    assert second["unchanged_index_version"] is None
    assert second["is_current"] is True
    assert _versions(engine, first["knowledge_set_id"]) == 2


def test_membership_and_embedding_must_both_match(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "match.txt")
    payload = ingestion_draft([document["id"]], config, name="Match", schema_version=2)
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    first = _run(client, engine, project_id, version)
    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(first["id"]))
        index = session.get(IndexVersion, UUID(first["published_index_id"]))
        runs = list(
            session.scalars(
                select(IngestionRunItem.processing_run_id).where(
                    IngestionRunItem.run_id == run.id
                )
            )
        )
        embedding = run.snapshot["embedding"]
        assert (
            indexes.unchanged_current_index(
                session, run.project_id, run.knowledge_set_id, runs, embedding=embedding
            ).id
            == index.id
        )
        assert (
            indexes.unchanged_current_index(
                session,
                run.project_id,
                run.knowledge_set_id,
                runs,
                embedding={**embedding, "model": "another-model"},
            )
            is None
        )
        assert (
            indexes.unchanged_current_index(
                session, run.project_id, run.knowledge_set_id, [], embedding=embedding
            )
            is None
        )
        # A source revision the current version does not hold is a change.
        assert (
            indexes.unchanged_current_index(
                session,
                run.project_id,
                run.knowledge_set_id,
                runs,
                embedding=embedding,
                source_revision_ids=[run.id],
            )
            is None
        )
        # Without a current ready version there is nothing to keep.
        knowledge_set = session.get(KnowledgeSet, run.knowledge_set_id)
        knowledge_set.current_ready_index_id = None
        session.flush()
        assert (
            indexes.unchanged_current_index(
                session, run.project_id, run.knowledge_set_id, runs, embedding=embedding
            )
            is None
        )
        session.rollback()


def test_completion_check_accepts_only_a_recorded_unchanged_version(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "check.txt")
    payload = ingestion_draft([document["id"]], config, name="Check", schema_version=2)
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    _run(client, engine, project_id, version)
    again = _run(client, engine, project_id, version)
    from sqlalchemy.exc import IntegrityError

    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(again["id"]))
        run.unchanged_index_id = None
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    with Session(engine) as session:
        nodes = session.scalars(
            select(IngestionRunNode.status).where(
                IngestionRunNode.run_id == UUID(again["id"])
            )
        ).all()
        assert nodes and set(nodes) == {"succeeded"}
