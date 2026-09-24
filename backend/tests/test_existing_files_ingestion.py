from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from uuid import UUID

import pymupdf
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.connectors.existing_files import ExistingFilesConnector
from app.ingestion_content.extractors.pdf import installed_ocr_languages
from app.models.document import Chunk, ProcessingRun
from app.models.derivation import ChunkBlockSpan
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun, IngestionRunItem, IngestionRunNode
from app.models.pipeline import Pipeline, PipelineVersion
from app.providers import embeddings
from app.services import ingestion_execution
from app.workers.indexing import process_index
from app.workers.dispatcher import dispatch_ingestion_once
from app.workers.ingestion import process_ingestion
from app.workers.processing import now, process
from app.workers.previews import process_preview
from test_documents import documents_api, pdf_bytes, start, upload  # noqa: F401
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
                    "profile": "standard-v1",
                    "config_version": "deterministic-clean-v1",
                }
                if schema_version == 2
                else {}
            ),
        },
        {
            "id": "chunk",
            "type": "chunk",
            "size": size,
            "overlap": 10,
            **(
                {"config_version": "character-window-v1"} if schema_version == 2 else {}
            ),
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
