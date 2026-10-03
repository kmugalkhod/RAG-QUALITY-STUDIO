import os
import subprocess
import sys
from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.connectors.website import PreviewOutcome, WebsiteArtifact
from app.core.config import settings
from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun, IngestionSchedule
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.source import (
    IndexSourceRevision,
    SourceItem,
    SourceRevision,
    SourceSnapshot,
    SourceSnapshotMember,
    WebsiteCrawlFrontier,
    WebsiteRunItem,
)
from app.pipelines.web_content import chunk_sections, extract_sections
from app.providers import embeddings
from app.schemas.ingestion import CleanNode
from app.services import ingestion
from app.workers.dispatcher import dispatch_ingestion_once
from app.workers.indexing import process_index
from app.workers.ingestion import process_ingestion
from app.workers.processing import now
from test_documents import documents_api  # noqa: F401
from test_indexes import ProviderDouble
from test_ingestion_contracts import ingestion_draft


def page(url, body, *, unchanged=False, depth=0, etag=None):
    return (
        PreviewOutcome(
            external_id=url,
            display_name=url,
            canonical_location=url,
            media_type="text/html",
            status="included",
            reason="HTML page is within scope and fetchable.",
            size_bytes=len(body),
            depth=depth,
        ),
        WebsiteArtifact(
            canonical_location=url,
            content=body,
            media_type="text/html",
            etag=etag,
            last_modified=None,
            validator_unchanged=unchanged,
            depth=depth,
        ),
    )


class WebsiteDouble:
    def __init__(self, pages, captured):
        self.pages = pages
        self.captured = captured
        self.policies = []

    def crawl(self, config, policy, priors, store):
        outcomes, artifacts = self.fetch_all(config, policy, priors)
        return store.import_results(outcomes, artifacts)

    def fetch_all(self, config, policy, priors):
        self.captured.append(priors)
        self.policies.append(policy)
        return [value[0] for value in self.pages], [
            value[1] for value in self.pages if value[1]
        ]


@pytest.fixture
def website_api(documents_api, monkeypatch):  # noqa: F811
    client, engine, project_id, other_project_id = documents_api
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    config = embeddings.configured()
    provider = ProviderDouble()
    monkeypatch.setattr(embeddings, "provider_for", lambda _: provider)
    yield client, engine, project_id, other_project_id, config, provider
    with Session(engine) as session:
        project_uuid = UUID(project_id)
        project_ids = [project_uuid, UUID(other_project_id)]
        indexes = select(IndexVersion.id).where(IndexVersion.project_id == project_uuid)
        runs = select(IngestionRun.id).where(IngestionRun.project_id == project_uuid)
        pipelines = select(Pipeline.id).where(Pipeline.project_id.in_(project_ids))
        revisions = session.scalars(
            select(SourceRevision).where(SourceRevision.project_id == project_uuid)
        ).all()
        processing = [revision.processing_run_id for revision in revisions]
        documents = [revision.document_id for revision in revisions]
        session.execute(
            update(IndexVersion)
            .where(IndexVersion.id.in_(indexes))
            .values(source_snapshot_id=None)
        )
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id.in_(runs))
            .values(source_snapshot_id=None)
        )
        snapshots = select(SourceSnapshot.id).where(
            SourceSnapshot.project_id == project_uuid
        )
        session.execute(
            delete(SourceSnapshotMember).where(
                SourceSnapshotMember.snapshot_id.in_(snapshots)
            )
        )
        session.execute(
            delete(SourceSnapshot).where(SourceSnapshot.project_id == project_uuid)
        )
        session.execute(
            delete(IndexSourceRevision).where(IndexSourceRevision.index_id.in_(indexes))
        )
        session.execute(delete(IndexChunk).where(IndexChunk.index_id.in_(indexes)))
        session.execute(delete(IndexVersion).where(IndexVersion.id.in_(indexes)))
        session.execute(delete(WebsiteRunItem).where(WebsiteRunItem.run_id.in_(runs)))
        session.execute(
            update(IngestionSchedule)
            .where(IngestionSchedule.project_id == project_uuid)
            .values(last_run_id=None)
        )
        session.execute(delete(IngestionRun).where(IngestionRun.id.in_(runs)))
        session.execute(
            delete(IngestionSchedule).where(
                IngestionSchedule.project_id == project_uuid
            )
        )
        session.execute(
            delete(SourceRevision).where(SourceRevision.project_id == project_uuid)
        )
        session.execute(delete(Chunk).where(Chunk.run_id.in_(processing)))
        session.execute(delete(ProcessingRun).where(ProcessingRun.id.in_(processing)))
        session.execute(delete(Document).where(Document.id.in_(documents)))
        session.execute(delete(SourceItem).where(SourceItem.project_id == project_uuid))
        session.execute(
            delete(PipelineVersion).where(PipelineVersion.pipeline_id.in_(pipelines))
        )
        session.execute(delete(Pipeline).where(Pipeline.id.in_(pipelines)))
        session.commit()


def save_website(client, project_id, config):
    payload = ingestion_draft()
    embed = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "embed"
    )
    embed.update(
        provider=config.provider,
        model=config.model,
        dimensions=config.dimensions,
        config_version=config.revision,
    )
    chunk = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "chunk"
    )
    chunk.update(size=100, overlap=10)
    saved = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved.status_code == 201, saved.text
    return saved.json()


def start_run(
    client,
    project_id,
    version,
    *,
    reuse_stored=False,
    source_input=None,
    destination=None,
):
    body = (
        {"source_input": source_input, "destination": destination}
        if source_input is not None
        else {"reuse_stored": reuse_stored}
    )
    if destination is None:
        body.pop("destination", None)
    response = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs",
        json=body,
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_rechunks_stored_website_artifacts_without_connector_calls(website_api):
    client, engine, project_id, _, config, _provider = website_api
    version = save_website(client, project_id, config)
    first = start_run(client, project_id, version)
    first_index = publish(
        engine,
        first["id"],
        lambda: WebsiteDouble(
            [
                page(
                    "https://example.com/",
                    b"<main><h1>Guide</h1><p>"
                    + b"Stored content. " * 80
                    + b"</p></main>",
                    etag='"stored-v1"',
                )
            ],
            [],
        ),
    )
    changed = {
        "kind": "ingestion",
        "name": version["name"],
        "execution": version["execution"],
        "layout": version["layout"],
    }
    chunk = next(
        node for node in changed["execution"]["nodes"] if node["type"] == "chunk"
    )
    chunk.update(size=240, overlap=40)
    saved = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}/versions",
        json=changed,
    )
    assert saved.status_code == 201, saved.text
    reprocessed = start_run(client, project_id, saved.json(), reuse_stored=True)

    def unexpected_connector():
        raise AssertionError(
            "Offline reprocessing must not create a Website connector."
        )

    second_index = publish(engine, reprocessed["id"], unexpected_connector)
    result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{reprocessed['id']}"
    ).json()
    assert result["status"] == "succeeded"
    assert result["changed_count"] == 1
    assert result["published_index_id"] == str(second_index)
    assert str(second_index) != str(first_index)
    assert result["chunk_count"] > 1
    # Fresh and reused chunks both report where the page was fetched from.
    for index_id in (first_index, second_index):
        records = client.get(
            f"/api/projects/{project_id}/indexes/{index_id}/records?limit=5"
        ).json()["items"]
        assert records
        assert {record["source_url"] for record in records} == {"https://example.com/"}


def test_builds_independent_destination_from_ready_snapshot_without_network(
    website_api,
):
    client, engine, project_id, other_project_id, config, provider = website_api
    version = save_website(client, project_id, config)
    first = start_run(client, project_id, version)
    first_index = publish(
        engine,
        first["id"],
        lambda: WebsiteDouble(
            [
                page(
                    "https://example.com/",
                    b"<main><h1>Guide</h1><p>"
                    + b"Reusable content. " * 90
                    + b"</p></main>",
                )
            ],
            [],
        ),
    )
    snapshot_id = first["source_snapshot_id"]

    changed = {
        "kind": "ingestion",
        "name": version["name"],
        "execution": version["execution"],
        "layout": version["layout"],
    }
    chunk = next(
        node for node in changed["execution"]["nodes"] if node["type"] == "chunk"
    )
    chunk.update(size=240, overlap=40)
    saved = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}/versions",
        json=changed,
    )
    assert saved.status_code == 201, saved.text
    second = start_run(
        client,
        project_id,
        saved.json(),
        source_input={"kind": "snapshot", "source_snapshot_id": snapshot_id},
        destination={"kind": "new", "name": "Precise snapshot variant"},
    )

    def unexpected_connector():
        raise AssertionError("Snapshot mode must never construct a Website connector.")

    second_index = publish(engine, second["id"], unexpected_connector)
    result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}"
    ).json()
    assert result["status"] == "succeeded"
    assert result["knowledge_set_name"] == "Precise snapshot variant"
    assert result["source_snapshot_id"] == snapshot_id
    assert second_index != first_index
    with Session(engine) as session:
        first_row = session.get(IndexVersion, first_index)
        second_row = session.get(IndexVersion, second_index)
        assert first_row.knowledge_set_id != second_row.knowledge_set_id
        assert (
            first_row.source_snapshot_id
            == second_row.source_snapshot_id
            == UUID(snapshot_id)
        )
        assert first_row.chunk_count != second_row.chunk_count

    calls_before_compatible_variant = len(provider.calls)
    third = start_run(
        client,
        project_id,
        version,
        source_input={"kind": "snapshot", "source_snapshot_id": snapshot_id},
        destination={"kind": "new", "name": "Compatible snapshot variant"},
    )
    third_index = publish(engine, third["id"], unexpected_connector)
    assert third_index not in (first_index, second_index)
    assert len(provider.calls) == calls_before_compatible_variant

    pending = start_run(client, project_id, version)
    not_ready = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs",
        json={
            "source_input": {
                "kind": "snapshot",
                "source_snapshot_id": pending["source_snapshot_id"],
            },
            "destination": {"kind": "new", "name": "Not ready variant"},
        },
    )
    assert not_ready.status_code == 409
    client.post(f"/api/projects/{project_id}/ingestion-runs/{pending['id']}/cancel")

    with Session(engine) as session:
        other_destination = KnowledgeSet(
            project_id=UUID(other_project_id), name="Other project index"
        )
        session.add(other_destination)
        session.commit()
        other_destination_id = other_destination.id
    wrong_destination = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs",
        json={
            "source_input": {
                "kind": "snapshot",
                "source_snapshot_id": snapshot_id,
            },
            "destination": {
                "kind": "existing",
                "knowledge_set_id": str(other_destination_id),
            },
        },
    )
    assert wrong_destination.status_code == 404

    other_version = save_website(client, other_project_id, config)

    cross_project = client.post(
        f"/api/projects/{other_project_id}/pipelines/{other_version['pipeline_id']}"
        f"/versions/{other_version['id']}/ingestion-runs",
        json={
            "source_input": {
                "kind": "snapshot",
                "source_snapshot_id": snapshot_id,
            }
        },
    )
    assert cross_project.status_code == 404

    mismatched = saved.json()
    source = next(
        node for node in mismatched["execution"]["nodes"] if node["type"] == "source"
    )
    source["config"]["selection"]["url"] = "https://example.org/"
    source["config"]["allowed_origins"] = ["https://example.org"]
    mismatch_version = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}/versions",
        json={
            "kind": "ingestion",
            "name": version["name"],
            "execution": mismatched["execution"],
            "layout": mismatched["layout"],
        },
    )
    assert mismatch_version.status_code == 201, mismatch_version.text
    mismatch = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{mismatch_version.json()['id']}/ingestion-runs",
        json={
            "source_input": {
                "kind": "snapshot",
                "source_snapshot_id": snapshot_id,
            }
        },
    )
    assert mismatch.status_code == 409
    assert "different Website source settings" in mismatch.json()["detail"]


def publish(engine, run_id, factory):
    process_ingestion(UUID(run_id), engine, connector_factory=factory)
    with Session(engine) as session:
        index = session.scalar(
            select(IndexVersion).where(IndexVersion.ingestion_run_id == UUID(run_id))
        )
        run = session.get(IngestionRun, UUID(run_id))
        assert index is not None, (run.status, run.error)
        index_id = index.id
    process_ingestion(UUID(run_id), engine, connector_factory=factory)
    for _ in range(20):
        process_index(index_id, engine)
        with Session(engine) as session:
            if session.get(IndexVersion, index_id).status == "succeeded":
                break
    process_ingestion(UUID(run_id), engine, connector_factory=factory)
    return index_id


def test_html_extraction_prefers_main_and_keeps_heading_provenance():
    clean = CleanNode(id="clean", type="clean", repeated_boilerplate=["Cookie notice"])
    sections = extract_sections(
        b"<header>Site header</header><main><h1>Guide</h1><p>Cookie notice Useful text</p>"
        b"<script>ignore()</script><h2>Details</h2><p>More text</p></main><footer>Footer</footer>",
        clean,
    )
    assert [section.text for section in sections] == ["Useful text", "More text"]
    assert sections[0].path == ("Guide",)
    assert sections[1].path == ("Guide", "Details")
    chunks = chunk_sections(sections, 100, 10)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "Useful text\n\nMore text"
    assert chunks[0]["provenance"]["section_path"] == ["Guide"]


def test_html_chunking_combines_adjacent_short_elements():
    clean = CleanNode(id="clean", type="clean")
    sections = extract_sections(
        b"<main><h1>Agents</h1><p>Create agents</p>"
        b"<p>Use create_agent with a model and tools.</p></main>",
        clean,
    )
    chunks = chunk_sections(sections, 600, 80)
    assert [chunk["text"] for chunk in chunks] == [
        "Create agents\n\nUse create_agent with a model and tools."
    ]
    assert chunks[0]["provenance"]["section_path"] == ["Agents"]


def test_first_crawl_incremental_refresh_and_preserved_indexes(website_api):
    client, engine, project_id, _, config, provider = website_api
    version = save_website(client, project_id, config)
    first_pages = [
        page(
            "https://example.com/",
            b"<nav>Discard me</nav><main><h1>Orchard</h1><p>The orchard grows apples.</p></main>",
            etag='"root-v1"',
        ),
        page(
            "https://example.com/guide",
            b"<main><h1>Guide</h1><p>Harvest starts in September.</p></main>",
            etag='"guide-v1"',
        ),
        page(
            "https://example.com/old",
            b"<main><h1>Old</h1><p>This page will be removed.</p></main>",
            etag='"old-v1"',
        ),
    ]
    captured = []
    first = start_run(client, project_id, version)
    first_index = publish(
        engine,
        first["id"],
        lambda: WebsiteDouble(first_pages, captured),
    )
    assert captured == [{}]
    first_result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{first['id']}"
    ).json()
    assert first_result["status"] == "succeeded"
    assert first_result["new_count"] == 3
    assert first_result["published_index_id"] == str(first_index)
    assert (
        client.get(
            f"/api/projects/{website_api[3]}/ingestion-runs/{first['id']}"
        ).status_code
        == 404
    )
    first_provider_calls = len(provider.calls)

    root_body = first_pages[0][1].content
    second_pages = [
        page(
            "https://example.com/",
            root_body,
            unchanged=True,
            etag='"root-v1"',
        ),
        page(
            "https://example.com/guide",
            b"<main><h1>Guide</h1><p>Harvest now starts in October.</p></main>",
            etag='"guide-v2"',
        ),
        page(
            "https://example.com/new",
            b"<main><h1>Storage</h1><p>Apples use recycled paper boxes.</p></main>",
            etag='"new-v1"',
        ),
    ]
    second = start_run(client, project_id, version)
    second_index = publish(
        engine,
        second["id"],
        lambda: WebsiteDouble(second_pages, captured),
    )
    second_embedding_text = [
        text for call in provider.calls[first_provider_calls:] for text in call
    ]
    assert all("The orchard grows apples" not in text for text in second_embedding_text)
    assert set(captured[-1]) == {
        "https://example.com/",
        "https://example.com/guide",
        "https://example.com/old",
    }
    result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}"
    ).json()
    assert (result["new_count"], result["changed_count"]) == (1, 1)
    assert (result["unchanged_count"], result["removed_count"]) == (1, 1)
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}/items"
    ).json()
    assert items["total"] == 4
    assert {item["outcome"] for item in items["items"]} == {
        "new",
        "changed",
        "unchanged",
        "removed",
    }
    with Session(engine) as session:
        indexes = session.scalars(
            select(IndexVersion)
            .where(IndexVersion.id.in_([first_index, second_index]))
            .order_by(IndexVersion.version)
        ).all()
        assert [index.status for index in indexes] == ["succeeded", "succeeded"]
        assert indexes[0].version == 1 and indexes[1].version == 2
        assert session.scalar(select(func.count()).select_from(SourceRevision)) == 5
        root_revisions = session.scalar(
            select(func.count())
            .select_from(SourceRevision)
            .join(SourceItem)
            .where(SourceItem.canonical_location == "https://example.com/")
        )
        assert root_revisions == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(IndexSourceRevision)
                .where(IndexSourceRevision.index_id == second_index)
            )
            == 3
        )
    retrieval = client.post(
        f"/api/projects/{project_id}/retrieval",
        json={"index_id": str(second_index), "query": "paper boxes", "top_k": 5},
    )
    assert retrieval.status_code == 200, retrieval.text
    evidence = retrieval.json()["items"]
    assert any(item["source_url"] == "https://example.com/new" for item in evidence)
    assert any(item["section_path"] for item in evidence)
    assert len(provider.calls) >= 3


def test_ready_snapshot_has_exact_paginated_project_scoped_membership(website_api):
    client, engine, project_id, other_project_id, config, _provider = website_api
    version = save_website(client, project_id, config)
    run = start_run(client, project_id, version)
    assert run["source_snapshot_id"] is not None
    collecting = client.get(
        f"/api/projects/{project_id}/source-snapshots/{run['source_snapshot_id']}"
    )
    assert collecting.status_code == 200
    assert collecting.json()["status"] == "collecting"

    index_id = publish(
        engine,
        run["id"],
        lambda: WebsiteDouble(
            [
                page("https://example.com/a", b"<main><p>Alpha page.</p></main>"),
                page("https://example.com/b", b"<main><p>Beta page.</p></main>"),
            ],
            [],
        ),
    )
    snapshot_id = run["source_snapshot_id"]
    detail = client.get(f"/api/projects/{project_id}/source-snapshots/{snapshot_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "ready"
    assert detail.json()["included_count"] == 2
    assert detail.json()["downstream_index_count"] == 1
    assert detail.json()["source_identity"] == {
        "origins": ["https://example.com"],
        "selection_modes": ["single_url"],
    }

    first_page = client.get(
        f"/api/projects/{project_id}/source-snapshots/{snapshot_id}/items",
        params={"limit": 1, "offset": 0},
    ).json()
    second_page = client.get(
        f"/api/projects/{project_id}/source-snapshots/{snapshot_id}/items",
        params={"limit": 1, "offset": 1},
    ).json()
    assert first_page["total"] == second_page["total"] == 2
    assert first_page["items"][0]["ordinal"] == 0
    assert second_page["items"][0]["ordinal"] == 1
    assert {
        first_page["items"][0]["canonical_location"],
        second_page["items"][0]["canonical_location"],
    } == {"https://example.com/a", "https://example.com/b"}

    indexes = client.get(
        f"/api/projects/{project_id}/source-snapshots/{snapshot_id}/indexes"
    ).json()
    assert indexes["total"] == 1
    assert indexes["items"][0]["id"] == str(index_id)
    with Session(engine) as session:
        snapshot_members = set(
            session.execute(
                select(
                    SourceSnapshotMember.source_item_id,
                    SourceSnapshotMember.source_revision_id,
                ).where(SourceSnapshotMember.snapshot_id == UUID(snapshot_id))
            ).all()
        )
        index_members = set(
            session.execute(
                select(
                    IndexSourceRevision.source_item_id,
                    IndexSourceRevision.source_revision_id,
                ).where(IndexSourceRevision.index_id == index_id)
            ).all()
        )
        assert snapshot_members == index_members
        assert session.get(IndexVersion, index_id).source_snapshot_id == UUID(
            snapshot_id
        )

    assert (
        client.get(
            f"/api/projects/{other_project_id}/source-snapshots/{snapshot_id}"
        ).status_code
        == 404
    )
    isolated = client.get(f"/api/projects/{other_project_id}/source-snapshots").json()
    assert isolated["items"] == []
    assert isolated["total"] == 0
    assert (
        client.delete(
            f"/api/projects/{project_id}/source-snapshots/{snapshot_id}"
        ).status_code
        == 405
    )


def test_populated_upgrade_backfills_only_proven_website_lineage(website_api):
    client, engine, project_id, _, config, _provider = website_api
    version = save_website(client, project_id, config)
    first = start_run(client, project_id, version)
    first_index = publish(
        engine,
        first["id"],
        lambda: WebsiteDouble(
            [page("https://example.com/", b"<main><p>Legacy page.</p></main>")],
            [],
        ),
    )
    second = start_run(client, project_id, version, reuse_stored=True)

    def unexpected_connector():
        raise AssertionError("Stored-artifact lineage must not fetch the Website.")

    second_index = publish(
        engine,
        second["id"],
        unexpected_connector,
    )
    env = {
        **os.environ,
        "DATABASE_URL": os.environ["TEST_DATABASE_URL"],
        "LEGACY_PROJECT_ORG_ID": "org_test_legacy",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0017"],
        env=env,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
    )
    with Session(engine) as session:
        first_run = session.get(IngestionRun, UUID(first["id"]))
        second_run = session.get(IngestionRun, UUID(second["id"]))
        assert first_run.source_snapshot_id is not None
        assert second_run.source_snapshot_id == first_run.source_snapshot_id
        assert session.get(IndexVersion, first_index).source_snapshot_id == (
            first_run.source_snapshot_id
        )
        assert session.get(IndexVersion, second_index).source_snapshot_id == (
            first_run.source_snapshot_id
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceSnapshotMember)
                .where(SourceSnapshotMember.snapshot_id == first_run.source_snapshot_id)
            )
            == 1
        )


def test_failed_refresh_keeps_previous_ready_index(website_api):
    client, engine, project_id, _, config, _ = website_api
    version = save_website(client, project_id, config)
    initial = [
        page("https://example.com/", b"<main><p>Stable content stays ready.</p></main>")
    ]
    first = start_run(client, project_id, version)
    first_index = publish(engine, first["id"], lambda: WebsiteDouble(initial, []))
    failed_outcome = PreviewOutcome(
        external_id="https://example.com/missing",
        display_name="Missing",
        canonical_location="https://example.com/missing",
        media_type=None,
        status="failed",
        reason="Website returned HTTP 503.",
        error_code="http_status",
    )
    second = start_run(client, project_id, version)
    process_ingestion(
        UUID(second["id"]),
        engine,
        connector_factory=lambda: WebsiteDouble(
            [initial[0], (failed_outcome, None)], []
        ),
    )
    result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}"
    ).json()
    assert result["status"] == "failed"
    failed_snapshot = client.get(
        f"/api/projects/{project_id}/source-snapshots/{second['source_snapshot_id']}"
    ).json()
    assert failed_snapshot["status"] == "failed"
    assert failed_snapshot["included_count"] == 0
    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(second["id"]))
        assert session.get(IndexVersion, first_index).status == "succeeded"
        assert run.knowledge_set_id
        assert (
            session.get(IndexVersion, first_index).knowledge_set_id
            == run.knowledge_set_id
        )
        assert (
            session.get(KnowledgeSet, run.knowledge_set_id).current_ready_index_id
            == first_index
        )


def test_run_records_fetch_policy_and_recovery_reuses_it(website_api, monkeypatch):
    client, engine, project_id, _, config, _ = website_api
    version = save_website(client, project_id, config)
    run = start_run(client, project_id, version)
    recorded = run["fetch_policies"]["source-0"]
    assert recorded["user_agent"] == settings.website_user_agent
    assert (
        recorded["request_timeout_seconds"] == settings.website_request_timeout_seconds
    )
    with Session(engine) as session:
        snapshot = session.get(IngestionRun, UUID(run["id"])).snapshot
        assert snapshot["fetch_policies"] == {"source-0": recorded}
    # A server setting changed after the run started must not alter the run.
    monkeypatch.setattr(settings, "website_request_timeout_seconds", 45.0)
    monkeypatch.setattr(settings, "website_user_agent", "Changed/2")
    double = WebsiteDouble(
        [page("https://example.com/0", b"<main><p>Recorded policy page.</p></main>")],
        [],
    )
    publish(engine, run["id"], lambda: double)
    assert double.policies and all(value == recorded for value in double.policies)
    detail = client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}").json()
    assert detail["fetch_policies"]["source-0"] == recorded


def test_cancellation_duplicate_delivery_and_website_stale_window(website_api):
    client, engine, project_id, _, config, _ = website_api
    version = save_website(client, project_id, config)
    run = start_run(client, project_id, version)
    calls = []

    class CancellingDouble(WebsiteDouble):
        def fetch_all(self, config, policy, priors):
            calls.append("network")
            with Session(engine) as session:
                ingestion.cancel_run(session, UUID(project_id), UUID(run["id"]))
            return super().fetch_all(config, policy, priors)

    values = [
        page("https://example.com/", b"<main><p>Never commit this page.</p></main>")
    ]
    process_ingestion(
        UUID(run["id"]),
        engine,
        connector_factory=lambda: CancellingDouble(values, []),
    )
    process_ingestion(
        UUID(run["id"]), engine, connector_factory=lambda: WebsiteDouble(values, [])
    )
    assert calls == ["network"]
    with Session(engine) as session:
        assert session.get(IngestionRun, UUID(run["id"])).status == "cancelled"
        assert session.scalar(select(func.count()).select_from(SourceRevision)) == 0
    cancelled_snapshot = client.get(
        f"/api/projects/{project_id}/source-snapshots/{run['source_snapshot_id']}"
    ).json()
    assert cancelled_snapshot["status"] == "cancelled"

    stale = start_run(client, project_id, version)
    stale_id = UUID(stale["id"])
    with Session(engine) as session:
        job = session.get(IngestionRun, stale_id)
        job.status = "running"
        job.started_at = job.updated_at = now() - timedelta(seconds=181)
        session.commit()
    sent = []
    dispatch_ingestion_once(engine, send=lambda value: sent.append(value))
    with Session(engine) as session:
        assert session.get(IngestionRun, stale_id).status == "running"
    assert sent == []
    with Session(engine) as session:
        job = session.get(IngestionRun, stale_id)
        job.updated_at = now() - timedelta(seconds=3701)
        session.commit()
    dispatch_ingestion_once(engine, send=lambda value: sent.append(value))
    with Session(engine) as session:
        assert session.get(IngestionRun, stale_id).status == "queued"


def test_unfetched_page_fails_the_source_stage_without_a_removal(website_api):
    client, engine, project_id, _, config, _ = website_api
    version = save_website(client, project_id, config)
    stable = page("https://example.com/", b"<main><p>Stable content stays.</p></main>")
    guide = page("https://example.com/guide", b"<main><p>Guide content.</p></main>")
    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: WebsiteDouble([stable, guide], []))
    timed_out = PreviewOutcome(
        external_id="https://example.com/guide",
        display_name="https://example.com/guide",
        canonical_location="https://example.com/guide",
        media_type=None,
        status="failed",
        reason="The website request timed out.",
        error_code="request_timeout",
    )
    second = start_run(client, project_id, version)
    process_ingestion(
        UUID(second["id"]),
        engine,
        connector_factory=lambda: WebsiteDouble([stable, (timed_out, None)], []),
    )
    result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}"
    ).json()
    assert result["status"] == "failed"
    states = {state["node_type"]: state["status"] for state in result["node_states"]}
    # The page could not be fetched, so the Source stage failed; nothing is left running.
    assert states["source"] == "failed"
    assert "running" not in states.values()
    assert states["publish_index"] == "queued"
    with Session(engine) as session:
        outcomes = session.scalars(
            select(WebsiteRunItem.outcome).where(
                WebsiteRunItem.run_id == UUID(second["id"]),
                WebsiteRunItem.canonical_location == "https://example.com/guide",
            )
        ).all()
    assert outcomes == ["failed"]


def test_run_items_record_attempts_warnings_and_nested_sitemaps(website_api):
    client, engine, project_id, _, config, _ = website_api
    version = save_website(client, project_id, config)
    run = start_run(client, project_id, version)
    shell_outcome, shell_artifact = page(
        "https://example.com/0",
        b"<html><body><main><p>Loading the application shell.</p></main>"
        b"<div id='root'></div><script>render()</script></body></html>",
    )
    retried = PreviewOutcome(**{**shell_outcome.__dict__, "attempts": 2})
    sitemap = PreviewOutcome(
        external_id="https://example.com/sitemap.xml",
        display_name="https://example.com/sitemap.xml",
        canonical_location="https://example.com/sitemap.xml",
        media_type="application/xml",
        status="sitemap",
        reason="Nested sitemap; listed 1 page URLs for discovery.",
        attempts=1,
    )
    publish(
        engine,
        run["id"],
        lambda: WebsiteDouble([(sitemap, None), (retried, shell_artifact)], []),
    )
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    ).json()["items"]
    by_outcome = {item["outcome"]: item for item in items}
    assert by_outcome["sitemap"]["attempts"] == 1
    included = by_outcome["new"]
    assert included["attempts"] == 2
    assert [value["code"] for value in included["warnings"]] == [
        "likely_client_rendered"
    ]


class WorkerKilled(BaseException):
    """Stands in for a worker process dying mid-request; not a handled error."""


class CrawlSite:
    """A public site double: a home page linking to `pages` leaf pages."""

    def __init__(self, pages, kill_at=None):
        self.pages = pages
        self.kill_at = kill_at
        self.calls = []

    def request(self, url, address, timeout, headers, max_bytes):
        self.calls.append(url)
        if url == self.kill_at:
            raise WorkerKilled()
        html = {"content-type": "text/html"}
        if url.endswith("/robots.txt"):
            return 404, {}, b""
        if url == "https://example.com/":
            links = "".join(
                f"<a href='/page-{number}'>Page {number}</a>"
                for number in range(self.pages)
            )
            return 200, html, f"<main><p>Home of the site.</p>{links}</main>".encode()
        number = url.rsplit("-", 1)[-1]
        return (
            200,
            html,
            f"<main><p>Page {number} explains topic {number} in detail.</p></main>".encode(),
        )


def crawl_connector(site):
    from app.connectors.safe_http import SafeHttpClient
    from app.connectors.website import WebsiteConnector

    return WebsiteConnector(
        client=SafeHttpClient(
            resolver=lambda host, port, type: [
                (2, type, 6, "", ("93.184.216.34", port))
            ],
            transport=site,
        ),
        sleeper=lambda _: None,
    )


def save_crawl(client, project_id, config):
    payload = ingestion_draft()
    source = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "source"
    )
    source["config"].update(
        selection={"mode": "crawl", "start_url": "https://example.com/"},
        max_pages=10,
        max_depth=1,
        requests_per_second=5,
    )
    for node in payload["execution"]["nodes"]:
        if node["type"] == "embed":
            node.update(
                provider=config.provider,
                model=config.model,
                dimensions=config.dimensions,
                config_version=config.revision,
            )
        elif node["type"] == "chunk":
            node.update(size=100, overlap=10)
    saved = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved.status_code == 201, saved.text
    return saved.json()


def test_recovered_crawl_fetches_only_the_remaining_pages(website_api, monkeypatch):
    client, engine, project_id, _, config, _ = website_api
    monkeypatch.setattr(settings, "website_fetch_concurrency", 1)
    version = save_crawl(client, project_id, config)
    run = start_run(client, project_id, version)
    run_id = UUID(run["id"])

    first = CrawlSite(5, kill_at="https://example.com/page-3")
    with pytest.raises(WorkerKilled):
        process_ingestion(
            run_id, engine, connector_factory=lambda: crawl_connector(first)
        )
    with Session(engine) as session:
        job = session.get(IngestionRun, run_id)
        assert job.status == "running" and job.stage == "discovering"
        # Live progress: every discovered URL, and the pages already finished.
        assert (job.discovered_count, job.processed_count) == (6, 4)
        assert job.crawl_state["source-0"]["transferred_bytes"] > 0
        fetched = session.scalar(
            select(func.count())
            .select_from(WebsiteCrawlFrontier)
            .where(
                WebsiteCrawlFrontier.run_id == run_id,
                WebsiteCrawlFrontier.status == "fetched",
            )
        )
        assert fetched == 4
        # Recovery as the dispatcher performs it for a dead worker.
        job.status = "queued"
        job.execution_token = None
        job.failures += 1
        session.commit()

    second = CrawlSite(5)
    index_id = publish(engine, run["id"], lambda: crawl_connector(second))
    pages = [url for url in second.calls if not url.endswith("robots.txt")]
    assert pages == ["https://example.com/page-3", "https://example.com/page-4"]
    with Session(engine) as session:
        assert session.get(IndexVersion, index_id).status == "succeeded"
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceRevision)
                .where(SourceRevision.project_id == UUID(project_id))
            )
            == 6
        )
        # Raw crawl copies are released once each revision has its own artifact.
        assert (
            session.scalar(
                select(func.count())
                .select_from(WebsiteCrawlFrontier)
                .where(
                    WebsiteCrawlFrontier.run_id == run_id,
                    WebsiteCrawlFrontier.storage_name.is_not(None),
                )
            )
            == 0
        )
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    ).json()["items"]
    assert sorted(item["outcome"] for item in items) == ["new"] * 6


def test_stale_worker_cannot_write_and_redelivery_adds_no_revisions(
    website_api, monkeypatch
):
    from app.connectors.website import CrawlProgress, PageResult
    from app.services.website_crawl import RunCrawlStore

    client, engine, project_id, _, config, _ = website_api
    monkeypatch.setattr(settings, "website_fetch_concurrency", 1)
    version = save_crawl(client, project_id, config)
    run = start_run(client, project_id, version)
    run_id = UUID(run["id"])
    first = CrawlSite(3, kill_at="https://example.com/page-1")
    with pytest.raises(WorkerKilled):
        process_ingestion(
            run_id, engine, connector_factory=lambda: crawl_connector(first)
        )
    with Session(engine) as session:
        stale_token = session.get(IngestionRun, run_id).execution_token
    stale = RunCrawlStore(engine, run_id, stale_token, "source-0")
    with Session(engine) as session:
        job = session.get(IngestionRun, run_id)
        job.status = "queued"
        job.execution_token = None
        session.commit()
    index_id = publish(engine, run["id"], lambda: crawl_connector(CrawlSite(3)))

    entry = stale.next_queued()
    assert entry is not None  # The stale worker still believes a page is queued.
    accepted = stale.commit(
        (entry, PageResult(duplicate_outcome_for(entry.url))),
        [],
        CrawlProgress(transferred=0, elapsed_seconds=0),
    )
    assert accepted is False
    # A duplicate delivery of the finished run claims nothing and writes nothing.
    process_ingestion(
        run_id, engine, connector_factory=lambda: crawl_connector(CrawlSite(3))
    )
    with Session(engine) as session:
        assert session.get(IndexVersion, index_id).status == "succeeded"
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceRevision)
                .where(SourceRevision.project_id == UUID(project_id))
            )
            == 4
        )
        statuses = session.scalars(
            select(WebsiteCrawlFrontier.status).where(
                WebsiteCrawlFrontier.run_id == run_id
            )
        ).all()
        assert sorted(statuses) == ["fetched"] * 4


def duplicate_outcome_for(url):
    return PreviewOutcome(
        external_id=url,
        display_name=url,
        canonical_location=url,
        media_type="text/html",
        status="included",
        reason="Written by a stale worker.",
    )


class DuplicateSite:
    article = (
        "<main><h1>Guide</h1><p>"
        + "This guide explains how the product handles duplicate pages. " * 6
        + "</p></main>"
    ).encode()

    def __init__(self):
        self.calls = []

    def request(self, url, address, timeout, headers, max_bytes):
        self.calls.append(url)
        html = {"content-type": "text/html"}
        if url.endswith("/robots.txt"):
            return 404, {}, b""
        if url == "https://example.com/b":
            return (
                200,
                html,
                b"<html><head><link rel='canonical' href='/a'></head>"
                b"<body><main><p>Copy.</p></main></body></html>",
            )
        return 200, html, self.article


def test_duplicate_urls_and_content_publish_one_revision(website_api, monkeypatch):
    client, engine, project_id, _, config, _ = website_api
    monkeypatch.setattr(settings, "website_fetch_concurrency", 1)
    payload = ingestion_draft()
    for node in payload["execution"]["nodes"]:
        if node["type"] == "source":
            node["config"].update(
                selection={
                    "mode": "url_list",
                    "urls": [
                        "https://example.com/a",
                        "https://example.com/a/",
                        "https://example.com/a?utm_source=x",
                        "https://example.com/b",
                    ],
                },
                max_pages=10,
            )
        elif node["type"] == "embed":
            node.update(
                provider=config.provider,
                model=config.model,
                dimensions=config.dimensions,
                config_version=config.revision,
            )
        elif node["type"] == "chunk":
            node.update(size=100, overlap=10)
    saved = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved.status_code == 201, saved.text
    run = start_run(client, project_id, saved.json())
    site = DuplicateSite()
    publish(engine, run["id"], lambda: crawl_connector(site))
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceRevision)
                .where(SourceRevision.project_id == UUID(project_id))
            )
            == 1
        )
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    ).json()["items"]
    assert sorted(item["outcome"] for item in items) == [
        "duplicate",
        "duplicate",
        "duplicate",
        "new",
    ]
    reasons = " ".join(item["reason"] for item in items)
    assert "Same content as https://example.com/a" in reasons
    assert (
        "Tracking parameters were removed from https://example.com/a?utm_source=x"
        in (reasons)
    )
    assert "canonical URL" in reasons


# Fixes from the 2026-10-03 review, through the real per-page run path.


class EverydaySite(CrawlSite):
    """Home links that real sites have: mail, phone, scripts and a very long URL.

    Pages carry an ETag; a request with the matching If-None-Match gets 304.
    """

    def request(self, url, address, timeout, headers, max_bytes):
        if url == "https://example.com/":
            self.calls.append(url)
            links = "".join(
                f"<a href='/page-{number}'>Page {number}</a>"
                for number in range(self.pages)
            )
            extra = (
                "<a href='mailto:team@example.com'>Mail</a>"
                "<a href='mailto:team@example.com'>Mail</a>"
                "<a href='tel:+15550100'>Call</a>"
                "<a href='javascript:void(0)'>Menu</a>"
                f"<a href='/{'long/' * 700}'>Long</a>"
            )
            return (
                200,
                {"content-type": "text/html"},
                (f"<main><p>Home of the site.</p>{links}{extra}</main>".encode()),
            )
        if not url.endswith("/robots.txt") and headers.get("If-None-Match") == '"v1"':
            self.calls.append(url)
            return 304, {"etag": '"v1"'}, b""
        status, response_headers, body = super().request(
            url, address, timeout, headers, max_bytes
        )
        if status == 200:
            response_headers = {**response_headers, "etag": '"v1"'}
        return status, response_headers, body


def stored_files():
    return {path.name for path in settings.storage_path.iterdir() if path.is_file()}


def test_everyday_links_and_unchanged_refresh_use_the_real_crawl_path(
    website_api, monkeypatch
):
    client, engine, project_id, _, config, _ = website_api
    monkeypatch.setattr(settings, "website_fetch_concurrency", 2)
    version = save_crawl(client, project_id, config)
    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: crawl_connector(EverydaySite(3)))
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{first['id']}/items"
    ).json()["items"]
    assert not [item for item in items if item["outcome"] == "failed"]
    assert any("longer than" in item["reason"] for item in items)

    files_before = stored_files()
    second = start_run(client, project_id, version)
    site = EverydaySite(3)
    publish(engine, second["id"], lambda: crawl_connector(site))
    with Session(engine) as session:
        assert session.get(IngestionRun, UUID(second["id"])).status == "succeeded"
        rows = session.scalars(
            select(WebsiteCrawlFrontier).where(
                WebsiteCrawlFrontier.run_id == UUID(second["id"]),
                WebsiteCrawlFrontier.status == "fetched",
            )
        ).all()
        unchanged = [row for row in rows if row.validator_unchanged]
        assert len(unchanged) == 3
        # 304 pages are read again from their prior revision, not stored twice.
        # Never stored (no artifact state), as opposed to stored then released.
        assert all(row.artifact_state is None for row in unchanged)
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}/items"
    ).json()["items"]
    assert {
        item["outcome"]
        for item in items
        if item["outcome"] not in ("excluded", "duplicate")
    } == {"unchanged"}
    # Nothing changed, so no new page files remain.
    assert stored_files() - files_before == set()


def test_a_failed_page_commit_leaves_no_orphan_page_file(website_api, monkeypatch):
    from app.services import website_crawl

    client, engine, project_id, _, config, _ = website_api
    monkeypatch.setattr(settings, "website_fetch_concurrency", 1)
    version = save_crawl(client, project_id, config)
    run = start_run(client, project_id, version)
    original = website_crawl.RunCrawlStore._save_progress
    calls = {"count": 0}

    def failing(self, session, run_row):
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("database went away")
        return original(self, session, run_row)

    monkeypatch.setattr(website_crawl.RunCrawlStore, "_save_progress", failing)
    files_before = stored_files()
    try:
        process_ingestion(
            UUID(run["id"]),
            engine,
            connector_factory=lambda: crawl_connector(CrawlSite(3)),
        )
    except RuntimeError:
        pass
    assert calls["count"] >= 3
    with Session(engine) as session:
        referenced = set(
            session.scalars(
                select(WebsiteCrawlFrontier.storage_name).where(
                    WebsiteCrawlFrontier.storage_name.is_not(None)
                )
            ).all()
        )
    assert stored_files() - files_before <= referenced


def test_dispatcher_sweep_releases_bodies_of_ended_runs(website_api, monkeypatch):
    from app.services.website_crawl import release_terminal_bodies

    client, engine, project_id, _, config, _ = website_api
    monkeypatch.setattr(settings, "website_fetch_concurrency", 1)
    version = save_crawl(client, project_id, config)
    run = start_run(client, project_id, version)
    run_id = UUID(run["id"])
    with pytest.raises(WorkerKilled):
        process_ingestion(
            run_id,
            engine,
            connector_factory=lambda: crawl_connector(
                CrawlSite(4, kill_at="https://example.com/page-2")
            ),
        )
    with Session(engine) as session:
        names = session.scalars(
            select(WebsiteCrawlFrontier.storage_name).where(
                WebsiteCrawlFrontier.run_id == run_id,
                WebsiteCrawlFrontier.storage_name.is_not(None),
            )
        ).all()
        assert names
        # Still running: the sweep must not touch a live run's pages.
        assert release_terminal_bodies(engine) == 0
        job = session.get(IngestionRun, run_id)
        job.status = "cancelled"
        job.execution_token = None
        session.commit()
    assert release_terminal_bodies(engine) == len(names)
    assert not set(names) & stored_files()
    with Session(engine) as session:
        assert not session.scalars(
            select(WebsiteCrawlFrontier.storage_name).where(
                WebsiteCrawlFrontier.run_id == run_id,
                WebsiteCrawlFrontier.storage_name.is_not(None),
            )
        ).all()


def test_scope_too_large_is_reported_on_the_maximum_pages_field(website_api):
    client, _, project_id, _, config, _ = website_api
    payload = ingestion_draft()
    for node in payload["execution"]["nodes"]:
        if node["type"] == "source":
            node["config"].update(
                selection={"mode": "crawl", "start_url": "https://example.com/"},
                max_pages=1000,
                requests_per_second=0.1,
            )
        elif node["type"] == "embed":
            node.update(
                provider=config.provider,
                model=config.model,
                dimensions=config.dimensions,
                config_version=config.revision,
            )
    response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list), response.text
    issue = response.json()["detail"][0]
    assert issue["loc"][-2:] == ["website", "max_pages"]
    assert "Lower maximum pages" in issue["msg"]


class RedirectingRefreshSite(EverydaySite):
    """On refresh, the first page moved to a trailing-slash URL and is unchanged."""

    def request(self, url, address, timeout, headers, max_bytes):
        if url == "https://example.com/page-0":
            self.calls.append(url)
            return 301, {"location": "https://example.com/page-0/"}, b""
        if url == "https://example.com/page-0/":
            url = "https://example.com/page-0"
        return super().request(url, address, timeout, headers, max_bytes)


def test_unchanged_page_behind_a_new_redirect_refreshes_without_failing(
    website_api, monkeypatch
):
    client, engine, project_id, _, config, _ = website_api
    monkeypatch.setattr(settings, "website_fetch_concurrency", 1)
    version = save_crawl(client, project_id, config)
    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: crawl_connector(EverydaySite(2)))

    second = start_run(client, project_id, version)
    publish(engine, second["id"], lambda: crawl_connector(RedirectingRefreshSite(2)))
    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(second["id"]))
        assert run.status == "succeeded", run.error
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}/items"
    ).json()["items"]
    moved = next(
        item
        for item in items
        if item["canonical_location"] == "https://example.com/page-0/"
    )
    assert moved["outcome"] == "new"
    assert not [item for item in items if item["outcome"] == "failed"]
