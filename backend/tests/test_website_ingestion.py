from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.connectors.website import PreviewOutcome, WebsiteArtifact
from app.core.config import settings
from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.source import (
    IndexSourceRevision,
    SourceItem,
    SourceRevision,
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

    def fetch_all(self, config, priors):
        self.captured.append(priors)
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
        indexes = select(IndexVersion.id).where(IndexVersion.project_id == project_uuid)
        runs = select(IngestionRun.id).where(IngestionRun.project_id == project_uuid)
        pipelines = select(Pipeline.id).where(Pipeline.project_id == project_uuid)
        revisions = session.scalars(
            select(SourceRevision).where(SourceRevision.project_id == project_uuid)
        ).all()
        processing = [revision.processing_run_id for revision in revisions]
        documents = [revision.document_id for revision in revisions]
        session.execute(
            delete(IndexSourceRevision).where(IndexSourceRevision.index_id.in_(indexes))
        )
        session.execute(delete(IndexChunk).where(IndexChunk.index_id.in_(indexes)))
        session.execute(delete(IndexVersion).where(IndexVersion.id.in_(indexes)))
        session.execute(delete(WebsiteRunItem).where(WebsiteRunItem.run_id.in_(runs)))
        session.execute(delete(IngestionRun).where(IngestionRun.id.in_(runs)))
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


def start_run(client, project_id, version):
    response = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )
    assert response.status_code == 202, response.text
    return response.json()


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
    assert chunks[1]["provenance"]["section_path"] == ["Guide", "Details"]


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


def test_cancellation_duplicate_delivery_and_website_stale_window(website_api):
    client, engine, project_id, _, config, _ = website_api
    version = save_website(client, project_id, config)
    run = start_run(client, project_id, version)
    calls = []

    class CancellingDouble(WebsiteDouble):
        def fetch_all(self, config, priors):
            calls.append("network")
            with Session(engine) as session:
                ingestion.cancel_run(session, UUID(project_id), UUID(run["id"]))
            return super().fetch_all(config, priors)

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

    stale = start_run(client, project_id, version)
    stale_id = UUID(stale["id"])
    with Session(engine) as session:
        job = session.get(IngestionRun, stale_id)
        job.status = "running"
        job.started_at = now() - timedelta(seconds=181)
        session.commit()
    sent = []
    dispatch_ingestion_once(engine, send=lambda value: sent.append(value))
    with Session(engine) as session:
        assert session.get(IngestionRun, stale_id).status == "running"
    assert sent == []
    with Session(engine) as session:
        job = session.get(IngestionRun, stale_id)
        job.started_at = now() - timedelta(seconds=3661)
        session.commit()
    dispatch_ingestion_once(engine, send=lambda value: sent.append(value))
    with Session(engine) as session:
        assert session.get(IngestionRun, stale_id).status == "queued"
