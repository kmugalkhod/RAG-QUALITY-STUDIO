import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure, ConnectorIssue, DiscoveredItem
from app.connectors.notion import NotionArtifact, NotionPreviewOutcome, NotionSegment
from app.core.config import settings
from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun
from app.models.source import IndexSourceRevision, SourceItem, SourceRevision
from app.workers.ingestion import process_ingestion
from test_connections import KEY_1, encoded
from test_documents import documents_api  # noqa: F401
from test_ingestion_contracts import ingestion_draft
from test_website_ingestion import publish, start_run, website_api  # noqa: F401


NOW = datetime(2026, 9, 13, tzinfo=UTC)
PAGE_A = "11111111-1111-4111-8111-111111111111"
PAGE_B = "22222222-2222-4222-8222-222222222222"
PAGE_C = "33333333-3333-4333-8333-333333333333"


def notion_artifact(page_id, title, text, revision, *, unchanged=False):
    item = DiscoveredItem(
        external_id=page_id,
        display_name=title,
        canonical_location=f"notion://page/{page_id}",
        media_type="text/plain",
        provider_revision=f"last-edited:{revision}",
        modified_at=NOW,
        metadata={
            "page_id": page_id,
            "url": f"https://www.notion.so/{page_id}",
            "parent_type": "workspace",
            "parent_id": None,
            "last_edited_time": revision,
        },
    )
    return NotionArtifact(
        item=item,
        content=None if unchanged else text.encode(),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        segments=()
        if unchanged
        else (
            NotionSegment(
                text=text,
                block_id=f"block-{page_id}",
                block_type="paragraph",
                depth=0,
                section_path=(title,),
            ),
        ),
        fetched_at=NOW,
        unchanged=unchanged,
    )


class NotionDouble:
    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.denied = False
        self.priors = []

    def fetch_all(self, config, priors, processing_config_hash):
        if self.denied:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="permission_denied",
                    message="Notion denied access to the requested content.",
                    retryable=False,
                )
            )
        self.priors.append(priors)
        outcomes = [
            NotionPreviewOutcome(
                external_id=value.item.external_id,
                display_name=value.item.display_name,
                canonical_location=value.item.canonical_location,
                provider_revision=value.item.provider_revision,
                media_type=value.item.media_type,
                status="included",
                reason="Notion page is shared and ready to ingest.",
            )
            for value in self.artifacts
        ]
        return outcomes, self.artifacts


def save_notion(client, project_id, embedding, connection_id):
    payload = ingestion_draft()
    payload["name"] = "Notion ingestion"
    payload["execution"]["nodes"][0]["config"] = {
        "kind": "notion",
        "connection_id": connection_id,
        "selection": {"mode": "workspace"},
        "max_pages": 20,
        "max_api_pages": 50,
        "max_blocks_per_page": 100,
        "max_block_depth": 4,
        "max_text_chars": 10000,
        "request_timeout_seconds": 5,
    }
    embed = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "embed"
    )
    embed.update(
        provider=embedding.provider,
        model=embedding.model,
        dimensions=embedding.dimensions,
        config_version=embedding.revision,
    )
    chunk = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "chunk"
    )
    chunk.update(size=100, overlap=10)
    response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_notion_incremental_refresh_provenance_retrieval_and_permission_loss(
    website_api,  # noqa: F811
    monkeypatch,
):
    client, engine, project_id, _, embedding, provider = website_api
    monkeypatch.setattr(settings, "source_connections_enabled", True)
    monkeypatch.setattr(settings, "source_connection_active_key", "v1")
    monkeypatch.setattr(settings, "source_connection_keys", {"v1": encoded(KEY_1)})
    connection = client.post(
        f"/api/projects/{project_id}/source-connections",
        json={
            "name": "Research workspace",
            "credentials": {
                "kind": "notion",
                "integration_token": "fixture-notion-token",
            },
        },
    ).json()
    version = save_notion(client, project_id, embedding, connection["id"])
    first_connector = NotionDouble(
        [
            notion_artifact(
                PAGE_A,
                "Orchard",
                "The orchard grows apples in carefully managed research rows. " * 3,
                "2026-09-12T10:00:00.000Z",
            ),
            notion_artifact(
                PAGE_B,
                "Old manual",
                "This page will disappear from the next workspace refresh. " * 3,
                "2026-09-12T11:00:00.000Z",
            ),
        ]
    )
    first = start_run(client, project_id, version)
    first_index = publish(engine, first["id"], lambda _: first_connector)
    first_calls = len(provider.calls)

    second_connector = NotionDouble(
        [
            notion_artifact(
                PAGE_A,
                "Orchard",
                "The orchard grows apples in carefully managed research rows. " * 3,
                "2026-09-12T10:00:00.000Z",
                unchanged=True,
            ),
            notion_artifact(
                PAGE_C,
                "Packing",
                "Packing instructions require recycled paper boxes for apples. " * 3,
                "2026-09-13T10:00:00.000Z",
            ),
        ]
    )
    second = start_run(client, project_id, version)
    second_index = publish(engine, second["id"], lambda _: second_connector)
    result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}"
    ).json()
    assert (
        result["new_count"],
        result["unchanged_count"],
        result["removed_count"],
    ) == (
        1,
        1,
        1,
    )
    assert all(
        "orchard grows apples" not in text
        for call in provider.calls[first_calls:]
        for text in call
    )
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}/items"
    ).json()["items"]
    assert all(item["source_kind"] == "notion" for item in items)
    assert {item["outcome"] for item in items} == {"new", "unchanged", "removed"}

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SourceRevision)) == 3
        assert (
            session.scalar(
                select(func.count())
                .select_from(IndexSourceRevision)
                .where(IndexSourceRevision.index_id == second_index)
            )
            == 2
        )
        revision = session.scalar(
            select(SourceRevision)
            .join(SourceItem)
            .where(SourceItem.external_id == PAGE_C)
        )
        assert revision.provenance == {
            "connector_kind": "notion",
            "connector_version": "1",
            "notion_api_version": "2026-03-11",
            "connection_id": connection["id"],
            "page_id": PAGE_C,
            "parent_type": "workspace",
            "parent_id": None,
            "url": f"https://www.notion.so/{PAGE_C}",
            "last_edited_time": "2026-09-13T10:00:00.000Z",
        }

    retrieval = client.post(
        f"/api/projects/{project_id}/retrieval",
        json={"index_id": str(second_index), "query": "paper boxes", "top_k": 20},
    )
    assert retrieval.status_code == 200
    assert any(
        item["source_url"] == f"notion://page/{PAGE_C}"
        for item in retrieval.json()["items"]
    )

    second_connector.denied = True
    failed = start_run(client, project_id, version)
    process_ingestion(
        UUID(failed["id"]), engine, connector_factory=lambda _: second_connector
    )
    failed_result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{failed['id']}"
    ).json()
    assert failed_result["status"] == "failed"
    assert failed_result["error"] == "Notion denied access to the requested content."
    assert "fixture-notion-token" not in failed_result["error"]
    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(failed["id"]))
        assert (
            session.get(KnowledgeSet, run.knowledge_set_id).current_ready_index_id
            == second_index
        )
        assert session.get(IndexVersion, first_index).status == "succeeded"


def test_notion_pipeline_rejects_cross_project_connection(
    website_api,  # noqa: F811
    monkeypatch,
):
    client, _, project_id, other_project_id, embedding, _ = website_api
    monkeypatch.setattr(settings, "source_connections_enabled", True)
    monkeypatch.setattr(settings, "source_connection_active_key", "v1")
    monkeypatch.setattr(settings, "source_connection_keys", {"v1": encoded(KEY_1)})
    other = client.post(
        f"/api/projects/{other_project_id}/source-connections",
        json={
            "name": "Other workspace",
            "credentials": {
                "kind": "notion",
                "integration_token": "other-token",
            },
        },
    ).json()
    response = client.post(
        f"/api/projects/{project_id}/pipelines",
        json={
            **ingestion_draft(),
            "execution": {
                **ingestion_draft()["execution"],
                "nodes": [
                    {
                        **node,
                        "config": {
                            "kind": "notion",
                            "connection_id": other["id"],
                            "selection": {"mode": "workspace"},
                        },
                    }
                    if node["type"] == "source"
                    else {
                        **node,
                        **(
                            {
                                "provider": embedding.provider,
                                "model": embedding.model,
                                "dimensions": embedding.dimensions,
                                "config_version": embedding.revision,
                            }
                            if node["type"] == "embed"
                            else {}
                        ),
                    }
                    for node in ingestion_draft()["execution"]["nodes"]
                ],
            },
        },
    )
    assert response.status_code == 404
