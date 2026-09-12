from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.connectors.existing_files import ExistingFilesConnector
from app.models.document import ProcessingRun
from app.models.index import IndexChunk, IndexVersion
from app.models.ingestion import IngestionRun, IngestionRunItem
from app.models.pipeline import Pipeline, PipelineVersion
from app.providers import embeddings
from app.workers.indexing import process_index
from app.workers.dispatcher import dispatch_ingestion_once
from app.workers.ingestion import process_ingestion
from app.workers.processing import now, process
from app.workers.previews import process_preview
from test_documents import documents_api, start, upload  # noqa: F401
from test_indexes import ProviderDouble


def ingestion_draft(document_ids, config, *, name="Existing files", size=100):
    nodes = [
        {
            "id": "source",
            "type": "source",
            "config": {"kind": "existing_files", "document_ids": document_ids},
        },
        {"id": "extract", "type": "extract"},
        {"id": "clean", "type": "clean"},
        {
            "id": "chunk",
            "type": "chunk",
            "size": size,
            "overlap": 10,
        },
        {
            "id": "embed",
            "type": "embed",
            "provider": config.provider,
            "model": config.model,
            "dimensions": config.dimensions,
            "config_version": config.revision,
        },
        {
            "id": "publish",
            "type": "publish_index",
            "knowledge_set_name": name,
        },
    ]
    return {
        "kind": "ingestion",
        "name": name,
        "execution": {
            "schema_version": 1,
            "nodes": nodes,
            "edges": [
                {"source": left["id"], "target": right["id"]}
                for left, right in zip(nodes, nodes[1:])
            ],
        },
        "layout": {
            "positions": {
                node["id"]: {"x": 80, "y": 40 + number * 120}
                for number, node in enumerate(nodes)
            }
        },
    }


@pytest.fixture
def ingestion_api(documents_api, monkeypatch):  # noqa: F811
    client, engine, project_id, other_project_id = documents_api
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    monkeypatch.setattr(settings, "chat_model", "test/chat")
    monkeypatch.setattr(settings, "chat_models", ["test/chat"])
    config = embeddings.configured()
    provider = ProviderDouble()
    monkeypatch.setattr(embeddings, "provider_for", lambda _: provider)
    yield client, engine, project_id, other_project_id, config, provider
    with Session(engine) as session:
        project_ids = [UUID(project_id), UUID(other_project_id)]
        index_ids = select(IndexVersion.id).where(
            IndexVersion.project_id.in_(project_ids)
        )
        run_ids = select(IngestionRun.id).where(
            IngestionRun.project_id.in_(project_ids)
        )
        pipeline_ids = select(Pipeline.id).where(Pipeline.project_id.in_(project_ids))
        session.execute(delete(IndexChunk).where(IndexChunk.index_id.in_(index_ids)))
        session.execute(delete(IndexVersion).where(IndexVersion.id.in_(index_ids)))
        session.execute(
            delete(IngestionRunItem).where(IngestionRunItem.run_id.in_(run_ids))
        )
        session.execute(delete(IngestionRun).where(IngestionRun.id.in_(run_ids)))
        session.execute(
            delete(PipelineVersion).where(PipelineVersion.pipeline_id.in_(pipeline_ids))
        )
        session.execute(delete(Pipeline).where(Pipeline.id.in_(pipeline_ids)))
        session.commit()


def prepare(client, engine, project_id, *, name, size=100):
    document = upload(
        client,
        project_id,
        content=("abcdefghij " * 30).encode(),
        name=name,
    )
    run = start(client, project_id, document["id"], size=size, overlap=10)
    process(UUID(run["id"]), engine)
    return document, run


def test_existing_files_preview_run_publication_and_exact_answer_index(ingestion_api):
    client, engine, project_id, other_project_id, config, provider = ingestion_api
    first, first_processing = prepare(client, engine, project_id, name="first.txt")
    second, second_processing = prepare(client, engine, project_id, name="second.txt")
    payload = ingestion_draft([first["id"], second["id"]], config)
    preview = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    )
    assert preview.status_code == 202, preview.text
    preview_id = preview.json()["id"]
    process_preview(UUID(preview_id), engine)
    preview_result = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}"
    ).json()
    assert preview_result["included_count"] == 2
    preview_items = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}/items"
    ).json()["items"]
    assert all("will be reused" in item["reason"] for item in preview_items)
    cross_project = client.post(
        f"/api/projects/{other_project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    )
    assert cross_project.status_code == 404

    saved = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved.status_code == 201, saved.text
    version = saved.json()
    route = (
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )
    accepted = client.post(route)
    assert accepted.status_code == 202, accepted.text
    run = accepted.json()
    assert run["stage"] == "indexing" and run["discovered_count"] == 2
    assert client.post(route).status_code == 409

    process_ingestion(UUID(run["id"]), engine)
    with Session(engine) as session:
        index = session.scalar(
            select(IndexVersion).where(IndexVersion.ingestion_run_id == UUID(run["id"]))
        )
        assert index is not None
        index_id = index.id
    process_index(index_id, engine)
    process_ingestion(UUID(run["id"]), engine)
    process_ingestion(UUID(run["id"]), engine)

    complete = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}"
    ).json()
    assert complete["status"] == "succeeded" and complete["progress"] == 100
    assert complete["published_index_id"] == str(index_id)
    assert complete["published_count"] == 1
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items?limit=1"
    ).json()
    assert items["total"] == 2 and items["items"][0]["status"] == "succeeded"
    assert provider.calls

    with Session(engine) as session:
        index = session.get(IndexVersion, index_id)
        membership = set(
            session.scalars(
                select(IndexChunk.run_id).where(IndexChunk.index_id == index_id)
            )
        )
        assert index.status == "succeeded"
        assert membership == {
            UUID(first_processing["id"]),
            UUID(second_processing["id"]),
        }

    answer_nodes = [
        {"id": "question", "type": "question"},
        {"id": "retriever", "type": "retriever", "index_id": str(index_id), "top_k": 2},
        {"id": "prompt", "type": "prompt", "template": "{question}\n{context}"},
        {
            "id": "llm",
            "type": "llm",
            "model": "test/chat",
            "max_tokens": 512,
            "temperature": 0,
        },
        {"id": "answer", "type": "answer"},
    ]
    answer = client.post(
        f"/api/projects/{project_id}/pipelines",
        json={
            "name": "Exact published index",
            "execution": {
                "schema_version": 1,
                "nodes": answer_nodes,
                "edges": [
                    {"source": left["id"], "target": right["id"]}
                    for left, right in zip(answer_nodes, answer_nodes[1:])
                ],
            },
            "layout": {
                "positions": {
                    node["id"]: {"x": 80, "y": number * 100}
                    for number, node in enumerate(answer_nodes)
                }
            },
        },
    )
    assert answer.status_code == 201, answer.text


def test_mismatched_processing_is_fenced_and_cancellable(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    document, _ = prepare(client, engine, project_id, name="cancel.txt", size=100)
    payload = ingestion_draft([document["id"]], config, name="Cancelled set", size=120)
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    accepted = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )
    assert accepted.status_code == 202, accepted.text
    run = accepted.json()
    item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    ).json()["items"][0]
    assert item["processing_created"] is True and item["status"] == "processing"

    cancelled = client.post(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/cancel"
    ).json()
    assert cancelled["status"] == "cancelled"
    process_ingestion(UUID(run["id"]), engine)
    with Session(engine) as session:
        assert session.get(IngestionRun, UUID(run["id"])).attempts == 0
        assert (
            session.get(ProcessingRun, UUID(item["processing_run_id"])).status
            == "cancelled"
        )


def test_existing_file_discovery_order_and_stale_recovery(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    documents = [
        prepare(client, engine, project_id, name=f"ordered-{number}.txt")[0]
        for number in range(3)
    ]
    selected = [UUID(document["id"]) for document in reversed(documents)]
    with Session(engine) as session:
        connector = ExistingFilesConnector(session, UUID(project_id))
        connector.page_size = 2
        first = connector.discover({"kind": "existing_files", "document_ids": selected})
        second = connector.discover(
            {"kind": "existing_files", "document_ids": selected}, first.next_cursor
        )
        assert [item.external_id for item in first.items + second.items] == [
            str(document_id) for document_id in selected
        ]

    payload = ingestion_draft(
        [documents[0]["id"]], config, name="Stale recovery", size=120
    )
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    run = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    ).json()
    with Session(engine) as session:
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == UUID(run["id"]))
            .values(
                status="running",
                attempts=3,
                failures=2,
                started_at=now() - timedelta(minutes=4),
            )
        )
        processing_id = session.scalar(
            select(IngestionRunItem.processing_run_id).where(
                IngestionRunItem.run_id == UUID(run["id"])
            )
        )
        session.commit()
    sent = []
    dispatch_ingestion_once(engine, send=sent.append)
    with Session(engine) as session:
        recovered = session.get(IngestionRun, UUID(run["id"]))
        assert recovered.status == "failed" and recovered.failures == 3
        assert session.get(ProcessingRun, processing_id).status == "cancelled"
    assert sent == []
