"""Spec 0012, Slice 0: one reproduction per Part A bug that has a backend path.

Each test states the fixed behaviour. While the bug is present it is a strict
`xfail`; the slice that fixes the bug removes the marker.
"""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import default_structure_steps
from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun, IngestionRunItem, IngestionRunNode
from app.models.pipeline import Pipeline, PipelineVersion
from app.providers import embeddings
from app.schemas.ingestion import CleanNodeV2
from app.services import ingestion as ingestion_service
from app.services import ingestion_execution
from app.workers import indexing as indexing_worker
from app.workers.dispatcher import dispatch_ingestion_once
from app.workers.indexing import process_index
from app.workers.ingestion import process_ingestion
from app.workers.processing import now, process
from test_documents import documents_api, upload  # noqa: F401
from test_existing_files_ingestion import (  # noqa: F401
    embed_until_ready,
    ingestion_api,
    ingestion_draft,
    start_processed_run,
)


@pytest.fixture
def api(ingestion_api):  # noqa: F811
    return ingestion_api


def bug(item: str, reason: str):
    return pytest.mark.xfail(strict=True, reason=f"spec 0012 {item}: {reason}")


TEXT = b"Lanterns light the archive. " * 20

SECTION_TOKEN_V1 = {
    "algorithm": "section_token",
    "unit": "tokens",
    "tokenizer_version": "utf8-byte-v1",
    "target_tokens": 120,
    "maximum_tokens": 160,
    "overlap_tokens": 20,
    "add_heading_context": True,
    "config_version": "section-token-v1",
}


def _save(client, project_id, payload):
    return client.post(f"/api/projects/{project_id}/pipelines", json=payload)


def _start(client, project_id, version):
    return client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )


def _knowledge_set(engine, project_id, name):
    with Session(engine) as session:
        row = KnowledgeSet(project_id=UUID(project_id), name=name)
        session.add(row)
        session.commit()
        return row.id


def _version_saved_before_this_spec(engine, project_id, payload):
    """A saved version that publishes by name, written as older saves stored it."""
    with Session(engine) as session:
        pipeline = Pipeline(
            project_id=UUID(project_id), name=payload["name"], kind="ingestion"
        )
        session.add(pipeline)
        session.flush()
        version = PipelineVersion(
            pipeline_id=pipeline.id,
            project_id=UUID(project_id),
            version=1,
            name=payload["name"],
            execution=payload["execution"],
            layout=payload["layout"],
        )
        session.add(version)
        session.commit()
        return {"pipeline_id": str(pipeline.id), "id": str(version.id)}


def _indexed_run(client, engine, project_id, config, name):
    """A run whose immutable index exists and is waiting to embed."""
    run_id = start_processed_run(client, engine, project_id, config, name, [TEXT])
    process_ingestion(run_id, engine)
    with Session(engine) as session:
        index_id = session.scalar(
            select(IndexVersion.id).where(IndexVersion.ingestion_run_id == run_id)
        )
    assert index_id is not None
    return run_id, index_id


class ThrottledProvider:
    def embed(self, texts):
        raise embeddings.EmbeddingError(
            "Local embedding request budget reached. Retry after one minute.",
            throttled=True,
        )


# Publish Index --------------------------------------------------------------


def test_a1_new_index_with_an_existing_name_is_a_field_error(api):
    client, engine, project_id, _, config, _ = api
    _knowledge_set(engine, project_id, "Docs")
    document = upload(client, project_id, TEXT, "a1.txt")
    payload = ingestion_draft([document["id"]], config, name="Docs", schema_version=2)
    response = _save(client, project_id, payload)
    assert response.status_code == 422, response.text
    [issue] = response.json()["detail"]
    assert issue["loc"][-1] == "knowledge_set_name"


def test_a3_concurrent_start_loses_with_409(api, monkeypatch):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "a3.txt")
    payload = ingestion_draft(
        [document["id"]], config, name="A3 race", schema_version=2
    )
    version = _save(client, project_id, payload).json()
    original = ingestion_service._add_node_states

    def slow(session, run, execution):
        # Hold the first start open so the second one runs inside its window.
        time.sleep(0.6)
        return original(session, run, execution)

    monkeypatch.setattr(ingestion_service, "_add_node_states", slow)
    results = {}

    def start(name, delay):
        time.sleep(delay)
        with Session(
            engine.execution_options(isolation_level="READ COMMITTED")
        ) as session:
            try:
                ingestion_service.start_run(
                    session,
                    UUID(project_id),
                    UUID(version["pipeline_id"]),
                    UUID(version["id"]),
                )
                results[name] = "started"
            except HTTPException as exc:
                results[name] = exc.status_code
            except Exception as exc:  # the bug: a raw database error
                results[name] = type(exc).__name__

    threads = [
        threading.Thread(target=start, args=("first", 0)),
        threading.Thread(target=start, args=("second", 0.2)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert results == {"first": "started", "second": 409}, results


def test_a4_stale_failure_leaves_terminal_states(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "a4.txt")
    payload = ingestion_draft([document["id"]], config, name="A4", schema_version=2)
    version = _save(client, project_id, payload).json()
    run = _start(client, project_id, version).json()
    run_id = UUID(run["id"])
    ingestion_execution.transition(engine, run_id, node_type="extract")
    with Session(engine) as session:
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status="running",
                failures=2,
                updated_at=now() - timedelta(minutes=10),
            )
        )
        session.commit()
    dispatch_ingestion_once(engine, send=lambda _: None)
    with Session(engine) as session:
        assert session.get(IngestionRun, run_id).status == "failed"
        nodes = session.scalars(
            select(IngestionRunNode.status).where(IngestionRunNode.run_id == run_id)
        ).all()
        items = session.scalars(
            select(IngestionRunItem.status).where(IngestionRunItem.run_id == run_id)
        ).all()
    # Stages that never started stay queued; none may stay running.
    assert "running" not in nodes, nodes
    assert "processing" not in items, items


def test_a5_unpublished_index_has_no_published_version(api):
    client, engine, project_id, _, config, _ = api
    run_id, index_id = _indexed_run(client, engine, project_id, config, "A5")
    with Session(engine) as session:
        session.execute(
            update(IndexVersion)
            .where(IndexVersion.id == index_id)
            .values(status="failed", error="Embedding failed.", finished_at=now())
        )
        session.commit()
    process_ingestion(run_id, engine)
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run_id}").json()
    assert result["status"] == "failed"
    assert result["published_index_id"] is None
    assert result["published_index_version"] is None
    assert "prior_index_version" in result and "is_current" in result


def test_a6_live_index_finalizes_the_run_as_succeeded(api, monkeypatch):
    client, engine, project_id, _, config, _ = api
    run_id, index_id = _indexed_run(client, engine, project_id, config, "A6")
    embed_until_ready(engine, index_id)
    original = ingestion_execution.mark_terminal

    def failing(session, run, status, node_type=None):
        if status == "succeeded":
            raise RuntimeError("bookkeeping failed")
        return original(session, run, status, node_type=node_type)

    monkeypatch.setattr(ingestion_execution, "mark_terminal", failing)
    process_ingestion(run_id, engine)
    with Session(engine) as session:
        run = session.get(IngestionRun, run_id)
        knowledge_set = session.get(KnowledgeSet, run.knowledge_set_id)
        assert knowledge_set.current_ready_index_id == index_id
        assert run.status == "succeeded", run.error


def test_a7_saved_name_resolves_ignoring_case(api):
    client, engine, project_id, _, config, _ = api
    existing = _knowledge_set(engine, project_id, "Docs")
    document = upload(client, project_id, TEXT, "a7.txt")
    payload = ingestion_draft([document["id"]], config, name="docs", schema_version=2)
    version = _version_saved_before_this_spec(engine, project_id, payload)
    response = _start(client, project_id, version)
    assert response.status_code == 202, response.text
    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(response.json()["id"]))
        assert run.knowledge_set_id == existing


def test_a7_new_name_differing_in_case_is_a_field_error(api):
    client, engine, project_id, _, config, _ = api
    _knowledge_set(engine, project_id, "Docs")
    document = upload(client, project_id, TEXT, "a7b.txt")
    payload = ingestion_draft([document["id"]], config, name="DOCS", schema_version=2)
    response = _save(client, project_id, payload)
    assert response.status_code == 422, response.text


# Embed ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chunk",
    [
        {**SECTION_TOKEN_V1, "target_tokens": 600, "maximum_tokens": 16384},
        # Valid on its own, but the heading prefix can push it over 8,191 bytes.
        {**SECTION_TOKEN_V1, "target_tokens": 600, "maximum_tokens": 8191},
    ],
)
def test_a8_chunk_that_can_exceed_the_embed_limit_is_rejected(api, chunk):
    client, _, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "a8.txt")
    payload = ingestion_draft(
        [document["id"]],
        config,
        name="A8",
        schema_version=2,
        chunk_settings={**chunk, "config_version": "section-token-v2"},
    )
    response = _save(client, project_id, payload)
    assert response.status_code == 422, response.text
    [issue] = response.json()["detail"]
    assert issue["loc"][-1] == "maximum_tokens"


def test_a9_throttling_ends_after_fifteen_minutes(api, monkeypatch):
    client, engine, project_id, _, config, _ = api
    _, index_id = _indexed_run(client, engine, project_id, config, "A9")
    monkeypatch.setattr(embeddings, "provider_for", lambda _: ThrottledProvider())
    process_index(index_id, engine)
    start = now()
    monkeypatch.setattr(indexing_worker, "now", lambda: start + timedelta(minutes=16))
    process_index(index_id, engine)
    with Session(engine) as session:
        index = session.get(IndexVersion, index_id)
        assert index.status == "failed"
        assert "kept refusing requests (rate limit)" in index.error


def test_a10_run_says_why_it_waits(api, monkeypatch):
    client, engine, project_id, _, config, _ = api
    run_id, index_id = _indexed_run(client, engine, project_id, config, "A10")
    monkeypatch.setattr(embeddings, "provider_for", lambda _: ThrottledProvider())
    process_index(index_id, engine)
    process_ingestion(run_id, engine)
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run_id}").json()
    assert "Waiting for embedding request budget" in (result["waiting_reason"] or "")


def test_a11_usage_is_kept_when_the_run_is_cancelled_mid_request(api, monkeypatch):
    client, engine, project_id, _, config, _ = api
    run_id, index_id = _indexed_run(client, engine, project_id, config, "A11")

    class CancelledDuringRequest:
        def embed_with_usage(self, texts):
            with Session(engine) as session:
                session.execute(
                    update(IngestionRun)
                    .where(IngestionRun.id == run_id)
                    .values(status="cancelled", execution_token=None)
                )
                session.execute(
                    update(IndexVersion)
                    .where(IndexVersion.id == index_id)
                    .values(status="cancelled", execution_token=None)
                )
                session.commit()
            return [[1.0, 0.0, 0.0] for _ in texts], embeddings.EmbeddingUsage(
                100, 0.001
            )

    monkeypatch.setattr(embeddings, "provider_for", lambda _: CancelledDuringRequest())
    process_index(index_id, engine)
    with Session(engine) as session:
        index = session.get(IndexVersion, index_id)
        assert index.status == "cancelled"
        assert index.embedding_tokens == 100


# Chunk ------------------------------------------------------------------------


def test_a13_one_bad_chunk_value_gives_one_error(api):
    client, _, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "a13.txt")
    payload = ingestion_draft(
        [document["id"]],
        config,
        name="A13",
        schema_version=2,
        chunk_settings={**SECTION_TOKEN_V1, "target_tokens": 0},
    )
    response = _save(client, project_id, payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert len(detail) == 1, [issue["loc"] for issue in detail]
    assert detail[0]["loc"][-1] == "target_tokens"


def test_a14_processing_record_names_the_saved_chunker_version(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "a14.txt")
    payload = ingestion_draft(
        [document["id"]],
        config,
        name="A14",
        schema_version=2,
        chunk_settings=SECTION_TOKEN_V1,
    )
    version = _save(client, project_id, payload).json()
    run = _start(client, project_id, version).json()
    with Session(engine) as session:
        processing_ids = session.scalars(
            select(IngestionRunItem.processing_run_id).where(
                IngestionRunItem.run_id == UUID(run["id"])
            )
        ).all()
    for processing_id in processing_ids:
        process(processing_id, engine)
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    ).json()["items"]
    versions = items[0]["processing_versions"]
    assert versions["chunker"] == "section-token-v2"  # engine label kept for reuse
    assert versions["chunker_config_version"] == "section-token-v1"


# Clean ------------------------------------------------------------------------


def test_a20_clean_order_error_uses_plain_names(api):
    client, _, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "a20.txt")
    steps = deepcopy(default_structure_steps())
    unicode_at = next(
        i for i, s in enumerate(steps) if s["type"] == "unicode_normalize"
    )
    controls_at = next(
        i for i, s in enumerate(steps) if s["type"] == "remove_control_characters"
    )
    steps[unicode_at], steps[controls_at] = steps[controls_at], steps[unicode_at]
    payload = ingestion_draft(
        [document["id"]], config, name="A20", schema_version=2, clean_steps=steps
    )
    response = _save(client, project_id, payload)
    assert response.status_code == 422
    message = " ".join(issue["msg"] for issue in response.json()["detail"])
    assert "unicode_normalize" not in message
    assert "Normalize Unicode must run before Remove unsupported controls" in message


def test_a21_dehyphenation_counts_only_joined_words():
    steps = deepcopy(default_structure_steps())
    for step in steps:
        if step["type"] == "dehyphenate":
            step["mode"] = "conservative-compounds"
    node = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=steps,
    )
    extracted = build_extracted_document(
        [
            CanonicalInputSegment(
                text="Married-\ncouple families. The survey collects infor-\nmation.",
                page_number=1,
                block_type="paragraph",
            ),
            CanonicalInputSegment(
                text="| Married-couple | 110,800 |", page_number=2, block_type="table"
            ),
        ],
        media_type="text/plain",
    )
    cleaned = clean_document(
        extracted,
        node,
        cleaner_for_node(node),
        extractor_version="test",
        configuration_hash="d" * 64,
    )
    audit = next(a for a in cleaned.transforms if a.transform == "dehyphenate")
    assert "Married-couple families" in cleaned.blocks[0].text
    assert audit.metrics["change_count"] == 1
