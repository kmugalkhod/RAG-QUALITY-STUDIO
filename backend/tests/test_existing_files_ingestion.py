from concurrent.futures import ThreadPoolExecutor
import base64
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from uuid import UUID

import pymupdf
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth import Principal
from app.connectors.existing_files import ExistingFilesConnector
from app.ingestion_content.extractors.pdf import installed_ocr_languages
from app.models.document import Chunk, ProcessingRun
from app.models.derivation import ChunkBlockSpan
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun, IngestionRunItem, IngestionRunNode
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.preview import SourcePreview
from app.models.query import QueryRun
from app.models.security import ProjectMembership, UserIdentity
from app.providers import generation
from app.providers import embeddings
from app.services import derivations as derivation_service
from app.services import ingestion_execution
from app.workers.indexing import process_index
from app.workers.dispatcher import dispatch_ingestion_once
from app.workers.ingestion import process_ingestion
from app.workers.processing import now, process
from app.workers.previews import process_preview
from test_documents import (  # noqa: F401
    STRUCTURED_UPLOADS,
    documents_api,
    pdf_bytes,
    start,
    upload,
)
from test_indexes import ProviderDouble


def ingestion_draft(
    document_ids,
    config,
    *,
    name="Existing files",
    size=100,
    schema_version=1,
    normalize_whitespace=True,
    repeated_boilerplate=None,
    clean_steps=None,
    chunk_settings=None,
):
    nodes = [
        {
            "id": "source",
            "type": "source",
            "config": {"kind": "existing_files", "document_ids": document_ids},
        },
        {
            "id": "extract",
            "type": "extract",
            **(
                {"strategy": "native_text", "config_version": "native-text-v1"}
                if schema_version == 2
                else {}
            ),
        },
        {
            "id": "clean",
            "type": "clean",
            "normalize_whitespace": normalize_whitespace,
            "repeated_boilerplate": repeated_boilerplate or [],
            **(
                {
                    "profile": ("structure-aware-v1" if clean_steps else "standard-v1"),
                    "config_version": (
                        "structure-clean-v1"
                        if clean_steps
                        else "deterministic-clean-v1"
                    ),
                    **({"steps": clean_steps} if clean_steps else {}),
                }
                if schema_version == 2
                else {}
            ),
        },
        (
            {"id": "chunk", "type": "chunk", **chunk_settings}
            if chunk_settings is not None
            else {
                "id": "chunk",
                "type": "chunk",
                "size": size,
                "overlap": 10,
                **(
                    {"config_version": "character-window-v1"}
                    if schema_version == 2
                    else {}
                ),
            }
        ),
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
            "schema_version": schema_version,
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
        session.execute(delete(QueryRun).where(QueryRun.project_id.in_(project_ids)))
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


def test_all_released_formats_complete_preview_publish_and_answer_workflow(
    ingestion_api,
):
    client, engine, project_id, _, config, _ = ingestion_api
    documents = [
        upload(client, project_id, content=content, name=name)
        for name, content in STRUCTURED_UPLOADS
    ]
    payload = ingestion_draft(
        [document["id"] for document in documents],
        config,
        name="All structured formats",
        schema_version=2,
    )

    preview = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    )
    assert preview.status_code == 202, preview.text
    process_preview(UUID(preview.json()["id"]), engine)
    preview_result = client.get(
        f"/api/projects/{project_id}/source-previews/{preview.json()['id']}"
    ).json()
    assert preview_result["status"] == "succeeded"
    assert preview_result["included_count"] == len(STRUCTURED_UPLOADS)

    saved_response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved_response.status_code == 201, saved_response.text
    version = saved_response.json()
    run = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    ).json()
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items?limit=100"
    ).json()["items"]
    assert len(items) == len(STRUCTURED_UPLOADS)
    for item in items:
        process(UUID(item["processing_run_id"]), engine)

    run_id = UUID(run["id"])
    process_ingestion(run_id, engine)
    with Session(engine) as session:
        index = session.scalar(
            select(IndexVersion).where(IndexVersion.ingestion_run_id == run_id)
        )
        assert index is not None
        index_id = index.id
    process_index(index_id, engine)
    process_ingestion(run_id, engine)
    completed = client.get(f"/api/projects/{project_id}/ingestion-runs/{run_id}").json()
    assert completed["status"] == "succeeded"
    assert completed["published_count"] == 1
    with Session(engine) as session:
        assert session.scalar(
            select(text("count(distinct run_id)"))
            .select_from(IndexChunk)
            .where(IndexChunk.index_id == index_id)
        ) == len(STRUCTURED_UPLOADS)

    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion(
            "The structured sources are indexed [S1].",
            "test/chat",
            {"total_tokens": 12},
            None,
        ),
    ):
        answer = client.post(
            f"/api/projects/{project_id}/query-runs",
            json={
                "index_id": str(index_id),
                "question": "Which structured sources were prepared?",
                "top_k": len(STRUCTURED_UPLOADS),
            },
        )
    assert answer.status_code == 201, answer.text
    result = answer.json()
    assert result["status"] == "succeeded"
    evidence = result["snapshot"]["evidence"]
    assert evidence and any("Prepared" in item["text"] for item in evidence)


def test_sensitive_policy_redacts_preview_embedding_and_answer_evidence(
    ingestion_api, monkeypatch
):
    client, engine, project_id, _, config, provider = ingestion_api
    monkeypatch.setattr(settings, "artifact_encryption_enabled", True)
    monkeypatch.setattr(settings, "artifact_encryption_mode", "local-keyring")
    monkeypatch.setattr(settings, "artifact_active_key", "test-v1")
    monkeypatch.setattr(
        settings,
        "artifact_keys",
        {"test-v1": SecretStr(base64.b64encode(bytes(range(32))).decode())},
    )
    sensitive_value = "alex@example.test"
    document = upload(
        client,
        project_id,
        content=f"Synthetic owner {sensitive_value} approved the policy.".encode(),
        name="sensitive.txt",
    )
    payload = ingestion_draft(
        [document["id"]], config, name="Redacted evidence", schema_version=2
    )
    clean = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "clean"
    )
    clean["sensitive_data_policy"] = {"enabled": True}

    accepted = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    )
    assert accepted.status_code == 202, accepted.text
    preview_id = UUID(accepted.json()["id"])
    process_preview(preview_id, engine)
    preview = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}"
    ).json()
    assert preview["protected_content"] is True
    cleaned = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}"
        "/items/0/representations?stage=cleaned"
    ).json()
    assert sensitive_value not in str(cleaned)
    assert "[EMAIL]" in str(cleaned)

    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    run = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    ).json()
    item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    ).json()["items"][0]
    process(UUID(item["processing_run_id"]), engine)
    inspected = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{item['processing_run_id']}/derivations"
    ).json()
    cleaned_derivation = next(
        value for value in inspected["items"] if value["kind"] == "cleaned"
    )
    assert cleaned_derivation["sensitive_findings"]
    assert sensitive_value not in str(cleaned_derivation["sensitive_findings"])

    editor_id = UUID("10000000-0000-4000-8000-000000000001")
    with Session(engine) as session:
        session.add(UserIdentity(id=editor_id, external_subject="synthetic-editor"))
        session.flush()
        session.add(
            ProjectMembership(
                project_id=UUID(project_id), user_id=editor_id, role="editor"
            )
        )
        session.commit()
    try:
        with Session(engine) as session:
            ordinary = derivation_service.list_derivations(
                session,
                UUID(project_id),
                UUID(item["processing_run_id"]),
                Principal(editor_id, "synthetic-editor", None, "oidc"),
            )
            assert all(not value.sensitive_findings for value in ordinary["items"])
    finally:
        with Session(engine) as session:
            session.execute(delete(UserIdentity).where(UserIdentity.id == editor_id))
            session.commit()

    run_id = UUID(run["id"])
    process_ingestion(run_id, engine)
    with Session(engine) as session:
        index = session.scalar(
            select(IndexVersion).where(IndexVersion.ingestion_run_id == run_id)
        )
        assert index is not None
        index_id = index.id
    process_index(index_id, engine)
    process_ingestion(run_id, engine)
    assert sensitive_value not in str(provider.calls)
    assert "[EMAIL]" in str(provider.calls)

    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion(
            "The policy was approved [S1].", "test/chat", None, None
        ),
    ):
        answer = client.post(
            f"/api/projects/{project_id}/query-runs",
            json={
                "index_id": str(index_id),
                "question": "Who approved the policy?",
                "top_k": 2,
            },
        ).json()
    assert answer["status"] == "succeeded"
    assert sensitive_value not in str(answer["snapshot"])
    assert "[EMAIL]" in str(answer["snapshot"]["evidence"])


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


def mixed_pdf_bytes():
    with pymupdf.open() as document:
        native = document.new_page(width=612, height=792)
        native.insert_text(
            (54, 100),
            "Native content remains available while OCR handles the next page.",
            fontsize=14,
        )
        with pymupdf.open() as image_source:
            page = image_source.new_page(width=612, height=792)
            page.insert_text((72, 150), "Scanned quality policy evidence", fontsize=26)
            pixmap = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
        scan = document.new_page(width=612, height=792)
        scan.insert_image(scan.rect, stream=pixmap.tobytes("png"))
        output = BytesIO()
        document.save(output)
    return output.getvalue()


def robust_extract(payload, *, ocr_mode):
    extract = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "extract"
    )
    extract.update(
        {
            "strategy": "auto",
            "ocr": {"mode": ocr_mode, "languages": ["eng"], "deskew": False},
            "tables": "preserve",
            "quality_policy": "default-v1",
            "config_version": "layout-ocr-v1",
        }
    )
    return payload


def test_node_transitions_are_serialized_across_document_workers(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    document, _ = prepare(client, engine, project_id, name="parallel.txt")
    saved = client.post(
        f"/api/projects/{project_id}/pipelines",
        json=ingestion_draft([document["id"]], config),
    ).json()
    accepted = client.post(
        f"/api/projects/{project_id}/pipelines/{saved['pipeline_id']}"
        f"/versions/{saved['id']}/ingestion-runs"
    ).json()
    run_id = UUID(accepted["id"])

    node_types = ["extract", "clean", "chunk"] * 3
    with ThreadPoolExecutor(max_workers=len(node_types)) as executor:
        transitions = list(
            executor.map(
                lambda node_type: ingestion_execution.transition(
                    engine, run_id, node_type=node_type
                ),
                node_types,
            )
        )

    assert all(transitions)
    with Session(engine) as session:
        states = session.execute(
            select(IngestionRunNode.node_type, IngestionRunNode.status)
            .where(IngestionRunNode.run_id == run_id)
            .order_by(IngestionRunNode.ordinal)
        ).all()
    assert states[:3] == [
        ("source", "succeeded"),
        ("extract", "succeeded"),
        ("clean", "succeeded"),
    ]
    assert states[3] == ("chunk", "running")
    assert states[4:] == [("embed", "queued"), ("publish_index", "queued")]


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
    assert [state["status"] for state in run["node_states"]] == ["queued"] * 6
    assert client.post(route).status_code == 409

    process_ingestion(UUID(run["id"]), engine)
    indexing = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run['id']}"
    ).json()
    assert [state["status"] for state in indexing["node_states"]] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "succeeded",
        "running",
        "queued",
    ]
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
    assert [state["status"] for state in complete["node_states"]] == ["succeeded"] * 6
    assert complete["published_index_id"] == str(index_id)
    assert complete["published_count"] == 1
    filtered_runs = client.get(
        f"/api/projects/{project_id}/ingestion-runs?pipeline_version_id={version['id']}"
    ).json()
    assert filtered_runs["total"] == 1
    assert filtered_runs["items"][0]["id"] == run["id"]
    unrelated_runs = client.get(
        f"/api/projects/{project_id}/ingestion-runs"
        "?pipeline_version_id=00000000-0000-4000-8000-000000000000"
    ).json()
    assert unrelated_runs == {"items": [], "total": 0, "limit": 20, "offset": 0}
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


def test_v2_duplicate_decision_preserves_both_documents_and_indexes_canonical(
    ingestion_api,
):
    client, engine, project_id, _, config, _ = ingestion_api
    content = b"The duplicate policy applies to all employees and contractors."
    first = upload(client, project_id, content=content, name="canonical.txt")
    second = upload(client, project_id, content=content, name="mirror.txt")
    payload = ingestion_draft(
        [first["id"], second["id"]],
        config,
        name="Duplicate policy",
        schema_version=2,
    )
    saved = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    accepted = client.post(
        f"/api/projects/{project_id}/pipelines/{saved['pipeline_id']}"
        f"/versions/{saved['id']}/ingestion-runs"
    ).json()
    run_id = UUID(accepted["id"])
    with Session(engine) as session:
        processing_ids = list(
            session.scalars(
                select(IngestionRunItem.processing_run_id).where(
                    IngestionRunItem.run_id == run_id
                )
            )
        )
    for processing_id in processing_ids:
        process(processing_id, engine)
    process_ingestion(run_id, engine)

    page = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{run_id}/items?limit=10"
    ).json()
    assert len(page["items"]) == 2
    decisions = [item["duplicate_decision"] for item in page["items"]]
    assert {decision["outcome"] for decision in decisions} == {"retained", "excluded"}
    excluded = next(value for value in decisions if value["outcome"] == "excluded")
    assert excluded["method"] == "exact_raw_sha256"
    assert excluded["retained_identity"].startswith("project-file:")

    with Session(engine) as session:
        index = session.scalar(
            select(IndexVersion).where(IndexVersion.ingestion_run_id == run_id)
        )
        assert index is not None
        assert (
            session.scalar(
                select(text("count(distinct run_id)"))
                .select_from(IndexChunk)
                .where(IndexChunk.index_id == index.id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(text("count(*)"))
                .select_from(ProcessingRun)
                .where(ProcessingRun.id.in_(processing_ids))
            )
            == 2
        )


def test_processing_preview_is_ephemeral_paged_and_retryable(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    document, _ = prepare(client, engine, project_id, name="preview-v2.txt")
    payload = ingestion_draft(
        [document["id"]], config, name="Processing preview", schema_version=2
    )
    extract = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "extract"
    )
    extract["quality_policy"] = {
        "id": "default-v1",
        "thresholds": {},
        "warning_action": "publish",
        "failed_item_action": "fail",
    }
    before_indexes = client.get(f"/api/projects/{project_id}/indexes?limit=100").json()[
        "total"
    ]
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
    assert preview["status"] == "succeeded"
    assert preview["pass_count"] == 1 and preview["known_compute_ms"] >= 0
    assert preview["fetch_mode"] == "cached-artifact"
    assert preview["cost_basis"]["known_monetary_cost"] is None
    item = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}/items"
    ).json()["items"][0]
    assert item["quality_decision"] == "pass"
    assert item["processing_status"] == "succeeded"
    assert item["processing_config_hash"] == preview["configuration_hash"]
    for stage in ("raw", "extracted", "cleaned", "diff", "chunks"):
        page = client.get(
            f"/api/projects/{project_id}/source-previews/{preview_id}"
            f"/items/0/representations?stage={stage}&limit=1"
        )
        assert page.status_code == 200, page.text
        assert page.json()["total"] >= 1
        assert len(page.json()["items"]) == 1
    assert (
        client.get(f"/api/projects/{project_id}/indexes?limit=100").json()["total"]
        == before_indexes
    )

    with Session(engine) as session:
        row = session.get(SourcePreview, UUID(preview_id))
        row.expires_at = now() - timedelta(seconds=1)
        session.commit()
    assert (
        client.get(f"/api/projects/{project_id}/source-previews/{preview_id}").json()[
            "status"
        ]
        == "expired"
    )
    assert (
        client.get(
            f"/api/projects/{project_id}/source-previews/{preview_id}/items"
        ).status_code
        == 410
    )
    retried = client.post(
        f"/api/projects/{project_id}/source-previews/{preview_id}/retry"
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["id"] != preview_id


def test_mismatched_processing_is_fenced_and_cancellable(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    document, _ = prepare(client, engine, project_id, name="cancel.txt", size=100)
    payload = ingestion_draft(
        [document["id"]],
        config,
        name="Cancelled set",
        size=120,
        schema_version=2,
    )
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
    assert (
        client.get(
            f"/api/projects/{project_id}/processing-runs/"
            f"{item['processing_run_id']}/derivations"
        ).json()["total"]
        == 0
    )


def test_v2_failed_cleaning_exposes_no_partial_derivations(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    document, _ = prepare(client, engine, project_id, name="too-long.txt", size=100)
    payload = ingestion_draft(
        [document["id"]], config, name="Bounded clean", schema_version=2
    )
    clean = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "clean"
    )
    clean["maximum_text_chars"] = 20
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    accepted = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    ).json()
    item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{accepted['id']}/items"
    ).json()["items"][0]

    process(UUID(item["processing_run_id"]), engine)

    with Session(engine) as session:
        processing = session.get(ProcessingRun, UUID(item["processing_run_id"]))
        assert processing.status == "failed"
        assert (
            session.scalar(select(Chunk).where(Chunk.run_id == processing.id).limit(1))
            is None
        )
    response = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{item['processing_run_id']}/derivations"
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_layout_capabilities_and_thumbnail_are_project_scoped(ingestion_api):
    client, engine, project_id, other_project_id, config, _ = ingestion_api
    capabilities = client.get(f"/api/projects/{project_id}/ingestion-capabilities")
    assert capabilities.status_code == 200, capabilities.text
    assert {profile["id"] for profile in capabilities.json()["profiles"]} == {
        "auto",
        "native",
        "layout_aware",
    }
    assert (
        client.get(
            f"/api/projects/{other_project_id}/ingestion-capabilities"
        ).status_code
        == 200
    )

    document = upload(
        client,
        project_id,
        pdf_bytes(
            ["Robust ingestion PDF has enough native text for layout inspection."]
        ),
        "layout.pdf",
    )
    payload = ingestion_draft(
        [document["id"]], config, name="Layout extraction", schema_version=2
    )
    extract = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "extract"
    )
    extract.update(
        {
            "strategy": "layout_aware",
            "ocr": {"mode": "off", "languages": ["eng"]},
            "tables": "preserve",
            "quality_policy": "default-v1",
            "config_version": "layout-ocr-v1",
        }
    )
    preview = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    )
    assert preview.status_code == 202, preview.text
    process_preview(UUID(preview.json()["id"]), engine)
    preview_items = client.get(
        f"/api/projects/{project_id}/source-previews/{preview.json()['id']}/items"
    ).json()["items"]
    assert preview_items[0]["status"] == "included"
    assert "initial schema-v2 processing" in preview_items[0]["reason"]
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert version.status_code == 201, version.text
    accepted = client.post(
        f"/api/projects/{project_id}/pipelines/{version.json()['pipeline_id']}"
        f"/versions/{version.json()['id']}/ingestion-runs"
    ).json()
    item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{accepted['id']}/items"
    ).json()["items"][0]
    assert item["processing_created"] is True
    process(UUID(item["processing_run_id"]), engine)
    with Session(engine) as session:
        assert session.get(ProcessingRun, UUID(item["processing_run_id"])).status == (
            "succeeded"
        )

    thumbnail_path = (
        f"/api/projects/{project_id}/processing-runs/"
        f"{item['processing_run_id']}/pages/1/thumbnail"
    )
    thumbnail = client.get(thumbnail_path)
    assert thumbnail.status_code == 200, thumbnail.text
    assert thumbnail.headers["content-type"] == "image/png"
    assert thumbnail.headers["x-content-type-options"] == "nosniff"
    assert thumbnail.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert (
        client.get(
            thumbnail_path.replace(
                f"projects/{project_id}", f"projects/{other_project_id}"
            )
        ).status_code
        == 404
    )


def test_quality_rejection_preserves_previous_ready_index(ingestion_api):
    if "eng" not in installed_ocr_languages():
        pytest.skip("The deterministic container OCR engine is not installed.")
    client, engine, project_id, _, config, _ = ingestion_api
    document = upload(
        client,
        project_id,
        mixed_pdf_bytes(),
        "mixed-quality.pdf",
    )
    successful_payload = robust_extract(
        ingestion_draft(
            [document["id"]],
            config,
            name="Quality-gated set",
            schema_version=2,
        ),
        ocr_mode="auto",
    )
    successful_version = client.post(
        f"/api/projects/{project_id}/pipelines", json=successful_payload
    ).json()
    successful_run = client.post(
        f"/api/projects/{project_id}/pipelines/"
        f"{successful_version['pipeline_id']}/versions/"
        f"{successful_version['id']}/ingestion-runs"
    ).json()
    successful_item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{successful_run['id']}/items"
    ).json()["items"][0]
    process(UUID(successful_item["processing_run_id"]), engine)
    process_ingestion(UUID(successful_run["id"]), engine)
    with Session(engine) as session:
        first_index = session.scalar(
            select(IndexVersion).where(
                IndexVersion.ingestion_run_id == UUID(successful_run["id"])
            )
        )
        assert first_index is not None
        first_index_id = first_index.id
        knowledge_set_id = first_index.knowledge_set_id
    process_index(first_index_id, engine)
    process_ingestion(UUID(successful_run["id"]), engine)
    process_ingestion(UUID(successful_run["id"]), engine)

    rejected_payload = robust_extract(
        ingestion_draft(
            [document["id"]],
            config,
            name="Quality-gated set",
            schema_version=2,
        ),
        ocr_mode="off",
    )
    rejected_version = client.post(
        f"/api/projects/{project_id}/pipelines", json=rejected_payload
    ).json()
    rejected_run = client.post(
        f"/api/projects/{project_id}/pipelines/{rejected_version['pipeline_id']}"
        f"/versions/{rejected_version['id']}/ingestion-runs"
    ).json()
    rejected_item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{rejected_run['id']}/items"
    ).json()["items"][0]
    process(UUID(rejected_item["processing_run_id"]), engine)
    process_ingestion(UUID(rejected_run["id"]), engine)

    rejected_result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{rejected_run['id']}"
    ).json()
    rejected_items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{rejected_run['id']}/items"
    ).json()["items"]
    assert rejected_result["status"] == "failed"
    assert rejected_items[0]["error"] == (
        "Extraction did not satisfy the saved quality policy. Review the source "
        "and extraction settings before retrying."
    )
    with Session(engine) as session:
        assert session.get(IndexVersion, first_index_id).status == "succeeded"
        assert (
            session.get(KnowledgeSet, knowledge_set_id).current_ready_index_id
            == first_index_id
        )
        assert (
            session.scalar(
                select(IndexVersion.id).where(
                    IndexVersion.ingestion_run_id == UUID(rejected_run["id"])
                )
            )
            is None
        )


def test_optional_quality_failure_excludes_only_selected_file(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    good = upload(
        client, project_id, b"The archive contains seven lanterns. " * 20, "good.txt"
    )
    bad = upload(
        client,
        project_id,
        ("The archive contains seven lanterns. " * 20 + "\ufffd").encode(),
        "optional-warning.txt",
    )
    payload = robust_extract(
        ingestion_draft(
            [good["id"], bad["id"]],
            config,
            name="Optional quality set",
            schema_version=2,
        ),
        ocr_mode="off",
    )
    source = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "source"
    )
    source["config"]["optional_document_ids"] = [bad["id"]]
    extract = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "extract"
    )
    extract["quality_policy"] = {
        "id": "strict-v1",
        "warning_action": "publish",
        "failed_item_action": "exclude",
    }
    saved_response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved_response.status_code == 201, saved_response.text
    saved = saved_response.json()
    run_response = client.post(
        f"/api/projects/{project_id}/pipelines/{saved['pipeline_id']}"
        f"/versions/{saved['id']}/ingestion-runs"
    )
    assert run_response.status_code == 202, run_response.text
    run = run_response.json()
    items_url = f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    items = client.get(items_url).json()["items"]
    for item in items:
        process(UUID(item["processing_run_id"]), engine)
    process_ingestion(UUID(run["id"]), engine)
    items = client.get(items_url).json()["items"]
    assert {
        (item["filename"], item["status"], item["is_optional"]) for item in items
    } == {
        ("good.txt", "ready", False),
        ("optional-warning.txt", "excluded", True),
    }, client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}").json()
    with Session(engine) as session:
        index = session.scalar(
            select(IndexVersion).where(IndexVersion.ingestion_run_id == UUID(run["id"]))
        )
        assert index is not None
        index_id = index.id
    process_index(index_id, engine)
    process_ingestion(UUID(run["id"]), engine)
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}").json()
    assert result["status"] == "succeeded", result
    assert result["failed_count"] == 1
    items = client.get(items_url).json()["items"]
    assert {item["filename"]: item["status"] for item in items} == {
        "good.txt": "succeeded",
        "optional-warning.txt": "excluded",
    }
    with Session(engine) as session:
        members = session.scalars(
            select(IndexChunk.run_id).where(IndexChunk.index_id == index_id).distinct()
        ).all()
        assert members == [
            UUID(
                next(
                    item["processing_run_id"]
                    for item in items
                    if item["filename"] == "good.txt"
                )
            )
        ]


def test_disallowed_language_excludes_required_file_and_publishes_good_file(
    ingestion_api,
):
    client, engine, project_id, _, config, _ = ingestion_api
    good = upload(
        client,
        project_id,
        b"The archive contains seven lanterns and the guide confirms this count. " * 8,
        "english.txt",
    )
    disallowed = upload(
        client,
        project_id,
        (
            "Le guide de la route et la carte de la ville sont pour la marche avec le groupe. "
            * 8
        ).encode(),
        "french.txt",
    )
    payload = robust_extract(
        ingestion_draft(
            [good["id"], disallowed["id"]],
            config,
            name="Language exclusion set",
            schema_version=2,
        ),
        ocr_mode="off",
    )
    extract = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "extract"
    )
    extract["language_policy"] = {
        "allowlist": ["en"],
        "disallowed_action": "exclude",
    }
    saved_response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved_response.status_code == 201, saved_response.text
    saved = saved_response.json()
    run_response = client.post(
        f"/api/projects/{project_id}/pipelines/{saved['pipeline_id']}"
        f"/versions/{saved['id']}/ingestion-runs"
    )
    assert run_response.status_code == 202, run_response.text
    run = run_response.json()
    items_url = f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    items = client.get(items_url).json()["items"]
    for item in items:
        process(UUID(item["processing_run_id"]), engine)
    with Session(engine) as session:
        failed = session.get(
            ProcessingRun,
            UUID(
                next(
                    item["processing_run_id"]
                    for item in items
                    if item["filename"] == "french.txt"
                )
            ),
        )
        assert failed.status == "failed"
        assert failed.error_code == "language_excluded"
    process_ingestion(UUID(run["id"]), engine)
    items = client.get(items_url).json()["items"]
    assert {
        item["filename"]: (item["status"], item["is_optional"]) for item in items
    } == {
        "english.txt": ("ready", False),
        "french.txt": ("excluded", False),
    }
    with Session(engine) as session:
        index = session.scalar(
            select(IndexVersion).where(IndexVersion.ingestion_run_id == UUID(run["id"]))
        )
        assert index is not None
        index_id = index.id
    process_index(index_id, engine)
    process_ingestion(UUID(run["id"]), engine)
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}").json()
    assert result["status"] == "succeeded", result
    assert result["failed_count"] == 1
    items = client.get(items_url).json()["items"]
    assert {item["filename"]: item["status"] for item in items} == {
        "english.txt": "succeeded",
        "french.txt": "excluded",
    }


def test_save_rejects_unavailable_ocr_pack_and_reports_only_dpi_error(ingestion_api):
    client, _, project_id, _, config, _ = ingestion_api
    document = upload(
        client, project_id, b"The archive contains seven lanterns.", "validation.txt"
    )
    payload = robust_extract(
        ingestion_draft([document["id"]], config, schema_version=2),
        ocr_mode="auto",
    )
    extract = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "extract"
    )
    extract["ocr"]["languages"] = ["fra"]
    unavailable = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert unavailable.status_code == 422
    assert "fra" in unavailable.json()["detail"]

    extract["ocr"]["languages"] = ["eng"]
    extract["ocr"]["dpi"] = 149
    invalid_dpi = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert invalid_dpi.status_code == 422
    issues = invalid_dpi.json()["detail"]
    relevant = [issue for issue in issues if issue["loc"][-2:] == ["ocr", "dpi"]]
    assert len(relevant) == 1
    assert (
        len(
            [
                issue
                for issue in issues
                if any("ingestion" in str(part).lower() for part in issue["loc"])
            ]
        )
        == 1
    )


def test_required_quality_failure_cancels_waiting_item(ingestion_api):
    client, engine, project_id, _, config, _ = ingestion_api
    good = upload(
        client, project_id, b"The archive contains seven lanterns. " * 20, "waiting.txt"
    )
    bad = upload(
        client,
        project_id,
        ("The archive contains seven lanterns. " * 20 + "\ufffd").encode(),
        "required-warning.txt",
    )
    payload = robust_extract(
        ingestion_draft(
            [good["id"], bad["id"]],
            config,
            name="Required quality set",
            schema_version=2,
        ),
        ocr_mode="off",
    )
    extract = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "extract"
    )
    extract["quality_policy"] = {
        "id": "strict-v1",
        "warning_action": "publish",
        "failed_item_action": "exclude",
    }
    saved = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    run = client.post(
        f"/api/projects/{project_id}/pipelines/{saved['pipeline_id']}"
        f"/versions/{saved['id']}/ingestion-runs"
    ).json()
    items_url = f"/api/projects/{project_id}/ingestion-runs/{run['id']}/items"
    items = client.get(items_url).json()["items"]
    process(
        UUID(
            next(
                item["processing_run_id"]
                for item in items
                if item["filename"] == "required-warning.txt"
            )
        ),
        engine,
    )
    process_ingestion(UUID(run["id"]), engine)
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}").json()
    assert result["status"] == "failed"
    items = client.get(items_url).json()["items"]
    assert {item["filename"]: item["status"] for item in items} == {
        "waiting.txt": "cancelled",
        "required-warning.txt": "failed",
    }


def test_v2_existing_files_executes_clean_config_and_reuses_exact_identity(
    ingestion_api,
):
    client, engine, project_id, other_project_id, config, _ = ingestion_api
    content = ("REMOVE  alpha\n\t beta   " * 10).encode()
    document = upload(client, project_id, content=content, name="v2-clean.txt")
    initial = start(client, project_id, document["id"], size=100, overlap=10)
    process(UUID(initial["id"]), engine)
    payload = ingestion_draft(
        [document["id"]],
        config,
        name="V2 cleaned",
        schema_version=2,
        normalize_whitespace=False,
        repeated_boilerplate=["REMOVE"],
    )
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload).json()
    accepted = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )
    assert accepted.status_code == 202, accepted.text
    item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{accepted.json()['id']}/items"
    ).json()["items"][0]
    assert item["processing_created"] is True
    process(UUID(item["processing_run_id"]), engine)

    with Session(engine) as session:
        processing = session.get(ProcessingRun, UUID(item["processing_run_id"]))
        chunks = session.scalars(
            select(Chunk.text)
            .where(Chunk.run_id == processing.id)
            .order_by(Chunk.ordinal)
        ).all()
        assert processing.status == "succeeded"
        assert processing.processing_config["versions"] == {
            "extractor": processing.parser_version,
            "cleaner": "deterministic-clean-v1",
            "chunker": "character-window-v1",
        }
        assert processing.processing_config_hash
        assert processing.output_hash
        assert "REMOVE" not in "".join(chunks)
        assert "\n\t beta" in "".join(chunks)

    derivations_response = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{item['processing_run_id']}/derivations"
    )
    assert derivations_response.status_code == 200, derivations_response.text
    derivations = derivations_response.json()["items"]
    assert [value["kind"] for value in derivations] == ["cleaned", "extracted"]
    assert all(value["schema_version"] == 1 for value in derivations)
    cleaned_derivation = next(
        value for value in derivations if value["kind"] == "cleaned"
    )
    blocks = client.get(
        f"/api/projects/{project_id}/content-derivations/"
        f"{cleaned_derivation['id']}/blocks?limit=1"
    )
    assert blocks.status_code == 200, blocks.text
    assert blocks.json()["total"] == 1
    assert blocks.json()["items"][0]["text"].startswith("  alpha")
    with Session(engine) as session:
        session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = session.execute(
            text(
                "EXPLAIN SELECT * FROM content_blocks "
                "WHERE derivation_id=:derivation_id ORDER BY ordinal LIMIT 20"
            ),
            {"derivation_id": cleaned_derivation["id"]},
        ).scalars()
        assert any("content_blocks_pkey" in line for line in plan)
    spans = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{item['processing_run_id']}/chunks/0/spans"
    )
    assert spans.status_code == 200, spans.text
    assert spans.json()["items"] == [
        {
            "run_id": item["processing_run_id"],
            "chunk_ordinal": 0,
            "span_ordinal": 0,
            "derivation_id": cleaned_derivation["id"],
            "derivation_kind": "cleaned",
            "block_ordinal": 0,
            "block_start_char": 0,
            "block_end_char": 100,
            "chunk_start_char": 0,
            "chunk_end_char": 100,
        }
    ]
    assert (
        client.get(
            f"/api/projects/{other_project_id}/processing-runs/"
            f"{item['processing_run_id']}/derivations"
        ).status_code
        == 404
    )
    extracted_derivation = next(
        value for value in derivations if value["kind"] == "extracted"
    )
    with Session(engine) as session, pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                ChunkBlockSpan(
                    run_id=UUID(item["processing_run_id"]),
                    chunk_ordinal=0,
                    span_ordinal=99,
                    derivation_id=UUID(extracted_derivation["id"]),
                    derivation_kind="cleaned",
                    block_ordinal=0,
                    block_start_char=0,
                    block_end_char=1,
                    chunk_start_char=0,
                    chunk_end_char=1,
                )
            )
            session.flush()

    client.post(
        f"/api/projects/{project_id}/ingestion-runs/{accepted.json()['id']}/cancel"
    )
    reuse_payload = ingestion_draft(
        [document["id"]],
        config,
        name="V2 exact reuse",
        schema_version=2,
        normalize_whitespace=False,
        repeated_boilerplate=["REMOVE"],
    )
    reuse_version = client.post(
        f"/api/projects/{project_id}/pipelines", json=reuse_payload
    ).json()
    reused = client.post(
        f"/api/projects/{project_id}/pipelines/{reuse_version['pipeline_id']}"
        f"/versions/{reuse_version['id']}/ingestion-runs"
    ).json()
    reused_item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{reused['id']}/items"
    ).json()["items"][0]
    assert reused_item["processing_created"] is False
    assert reused_item["processing_run_id"] == item["processing_run_id"]
    assert reused_item["processing_versions"]["cleaner"] == "deterministic-clean-v1"


def test_v2_structure_cleaning_persists_audits_and_reconstructs_scoped_diff(
    ingestion_api,
):
    from app.ingestion_content.cleaning import default_structure_steps

    client, engine, project_id, other_project_id, config, _ = ingestion_api
    content = ("Cafe\u0301\ufeff inter-\nnational REMOVE\n" * 8).encode()
    document = upload(client, project_id, content=content, name="structure-clean.txt")
    steps = default_structure_steps()
    steps.insert(
        -1,
        {
            "id": "literal",
            "type": "remove_literal_boilerplate",
            "enabled": True,
            "values": ["REMOVE"],
            "block_types": ["unknown"],
        },
    )
    payload = ingestion_draft(
        [document["id"]],
        config,
        name="Structure cleaned",
        schema_version=2,
        clean_steps=steps,
    )
    version = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert version.status_code == 201, version.text
    started = client.post(
        f"/api/projects/{project_id}/pipelines/{version.json()['pipeline_id']}"
        f"/versions/{version.json()['id']}/ingestion-runs"
    )
    assert started.status_code == 202, started.text
    item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{started.json()['id']}/items"
    ).json()["items"][0]
    assert item["processing_versions"]["cleaner"] == "structure-clean-v1"
    process(UUID(item["processing_run_id"]), engine)

    derivations = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{item['processing_run_id']}/derivations"
    ).json()["items"]
    cleaned_derivation = next(
        value for value in derivations if value["kind"] == "cleaned"
    )
    assert cleaned_derivation["engine_version"] == "structure-clean-v1"
    assert [audit["transform"] for audit in cleaned_derivation["transforms"]][0:3] == [
        "preserve_structure",
        "unicode_normalize",
        "remove_control_characters",
    ]
    assert any(
        audit["transform"] == "remove_literal_boilerplate"
        and audit["changed_blocks"] == 1
        for audit in cleaned_derivation["transforms"]
    )

    diff = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{item['processing_run_id']}/cleaning-diff?limit=1"
    )
    assert diff.status_code == 200, diff.text
    assert diff.json()["total"] == 1
    change = diff.json()["items"][0]
    assert change["action"] == "rewritten"
    assert "Cafe\u0301" in change["before_text"]
    assert "Café" in change["after_text"]
    assert "REMOVE" not in change["after_text"]
    assert "unicode_normalize" in change["transforms"]
    assert "remove_literal_boilerplate" in change["transforms"]
    assert (
        client.get(
            f"/api/projects/{other_project_id}/processing-runs/"
            f"{item['processing_run_id']}/cleaning-diff"
        ).status_code
        == 404
    )


def test_chunk_only_variant_reuses_derivations_and_parent_retrieval(ingestion_api):
    from app.ingestion_content.cleaning import default_structure_steps

    client, engine, project_id, _, config, provider = ingestion_api
    document = upload(
        client,
        project_id,
        content=(
            "Operational evidence remains faithful and inspectable. " * 24
        ).encode(),
        name="chunk-variant.txt",
    )
    section_payload = ingestion_draft(
        [document["id"]],
        config,
        name="Section chunk source",
        schema_version=2,
        clean_steps=default_structure_steps(),
        chunk_settings={
            "algorithm": "section_token",
            "target_tokens": 64,
            "maximum_tokens": 96,
            "overlap_tokens": 0,
            "add_heading_context": True,
            "config_version": "section-token-v1",
        },
    )
    section_version = client.post(
        f"/api/projects/{project_id}/pipelines", json=section_payload
    ).json()
    section_ingestion = client.post(
        f"/api/projects/{project_id}/pipelines/{section_version['pipeline_id']}"
        f"/versions/{section_version['id']}/ingestion-runs"
    ).json()
    section_item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{section_ingestion['id']}/items"
    ).json()["items"][0]
    process(UUID(section_item["processing_run_id"]), engine)
    section_derivations = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{section_item['processing_run_id']}/derivations"
    ).json()["items"]
    client.post(
        f"/api/projects/{project_id}/ingestion-runs/{section_ingestion['id']}/cancel"
    )

    parent_payload = ingestion_draft(
        [document["id"]],
        config,
        name="Parent child variant",
        schema_version=2,
        clean_steps=default_structure_steps(),
        chunk_settings={
            "algorithm": "parent_child",
            "child_target_tokens": 64,
            "child_maximum_tokens": 96,
            "child_overlap_tokens": 0,
            "parent_target_tokens": 192,
            "parent_maximum_tokens": 256,
            "add_heading_context": True,
            "config_version": "parent-child-v1",
        },
    )
    parent_version = client.post(
        f"/api/projects/{project_id}/pipelines", json=parent_payload
    ).json()
    parent_ingestion = client.post(
        f"/api/projects/{project_id}/pipelines/{parent_version['pipeline_id']}"
        f"/versions/{parent_version['id']}/ingestion-runs"
    ).json()
    parent_item = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{parent_ingestion['id']}/items"
    ).json()["items"][0]
    assert parent_item["processing_created"] is True
    process(UUID(parent_item["processing_run_id"]), engine)

    parent_derivations = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{parent_item['processing_run_id']}/derivations"
    ).json()["items"]
    assert {item["id"] for item in parent_derivations} == {
        item["id"] for item in section_derivations
    }
    chunks = client.get(
        f"/api/projects/{project_id}/processing-runs/"
        f"{parent_item['processing_run_id']}/chunks?limit=100"
    )
    assert chunks.status_code == 200, chunks.text
    inspected = chunks.json()
    parents = {
        item["ordinal"]: item
        for item in inspected["items"]
        if item["chunk_role"] == "parent"
    }
    children = [item for item in inspected["items"] if item["chunk_role"] == "child"]
    assert parents and children
    assert inspected["summary"]["parent_count"] == len(parents)
    assert inspected["summary"]["indexed_count"] == len(children)
    assert all(item["parent_ordinal"] in parents for item in children)
    assert all(item["spans"] for item in inspected["items"])
    with Session(engine) as session:
        parent_run = session.get(ProcessingRun, UUID(parent_item["processing_run_id"]))
        assert parent_run.reused_from_processing_run_id == UUID(
            section_item["processing_run_id"]
        )

    client.post(
        f"/api/projects/{project_id}/ingestion-runs/{parent_ingestion['id']}/cancel"
    )
    index_response = client.post(f"/api/projects/{project_id}/indexes")
    assert index_response.status_code == 202, index_response.text
    index = index_response.json()
    assert index["chunk_count"] == len(children)
    provider.calls.clear()
    process_index(UUID(index["id"]), engine)
    process_index(UUID(index["id"]), engine)
    assert 0 < sum(len(call) for call in provider.calls) <= len(children)
    embedded_inputs = {text for call in provider.calls for text in call}
    assert embedded_inputs <= {item["embedding_text"] for item in children}
    assert not embedded_inputs.intersection(
        {item["embedding_text"] for item in parents.values()}
        - {item["embedding_text"] for item in children}
    )
    retrieval = client.post(
        f"/api/projects/{project_id}/retrieval",
        json={"index_id": index["id"], "query": "abcd", "top_k": 1},
    )
    assert retrieval.status_code == 200, retrieval.text
    evidence = retrieval.json()["items"][0]
    assert evidence["chunk_role"] == "child"
    assert evidence["matched_chunk_ordinal"] == evidence["ordinal"]
    assert evidence["supplied_parent_ordinal"] in parents
    assert evidence["matched_text"] in evidence["text"]
    assert (
        evidence["text"]
        == parents[evidence["supplied_parent_ordinal"]]["evidence_text"]
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
