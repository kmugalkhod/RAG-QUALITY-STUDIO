"""Spec 0015 U3 and U4: pipelines open by their saved kind, and runs say which
extract, clean and chunk versions they used."""

from types import SimpleNamespace
from uuid import uuid4

from app.services.ingestion import _stage_versions
from test_existing_files_ingestion import ingestion_draft as files_draft
from test_ingestion_contracts import ingestion_draft
from test_pipelines import draft, pipeline_api  # noqa: F401
from test_queries import query_api  # noqa: F401
from test_indexes import index_api, embedding_config  # noqa: F401
from test_documents import documents_api  # noqa: F401

CONFIG = SimpleNamespace(
    provider="openrouter",
    model="openai/text-embedding-3-small",
    dimensions=1536,
    revision="1",
)


def test_a_pipeline_is_read_by_id_with_its_saved_kind(pipeline_api):  # noqa: F811
    from app.core.config import settings

    c, _, p, q, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    answer = c.post(base, json=draft(index["id"])).json()
    ingestion_payload = ingestion_draft()
    embed = next(
        n for n in ingestion_payload["execution"]["nodes"] if n["type"] == "embed"
    )
    embed.update(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        config_version=settings.embedding_revision,
    )
    ingestion = c.post(base, json=ingestion_payload)
    assert ingestion.status_code == 201, ingestion.text
    ingestion = ingestion.json()

    read = c.get(f"{base}/{answer['pipeline_id']}")
    assert read.status_code == 200, read.text
    assert read.json()["kind"] == "answer"
    assert read.json()["name"] == "Evidence pipeline"
    assert c.get(f"{base}/{ingestion['pipeline_id']}").json()["kind"] == "ingestion"
    # Another project's pipeline, an unknown ID and a malformed ID are not found.
    assert c.get(f"{base.replace(p, q)}/{answer['pipeline_id']}").status_code == 404
    missing = c.get(f"{base}/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Pipeline not found in this project."
    assert c.get(f"{base}/not-a-pipeline").status_code == 422
    # The fixed routes keep their meaning.
    assert c.get(f"{base}/options").status_code == 200


def test_stage_versions_list_each_saved_version_once():
    payload = files_draft(
        [str(uuid4())],
        CONFIG,
        schema_version=2,
        clean_steps=None,
        chunk_settings={
            "algorithm": "section_token",
            "config_version": "section-token-v5",
        },
    )
    assert _stage_versions(payload["execution"]) == {
        "extract": ["native-text-v1"],
        "clean": ["deterministic-clean-v1"],
        "chunk": ["section-token-v5"],
    }


def test_a_saved_chunker_without_a_version_reports_v1():
    payload = files_draft(
        [str(uuid4())],
        CONFIG,
        schema_version=2,
        chunk_settings={"algorithm": "parent_child"},
    )
    assert _stage_versions(payload["execution"])["chunk"] == ["parent-child-v1"]


def test_unreadable_snapshots_have_no_stage_versions():
    assert _stage_versions(None) is None
    assert _stage_versions({"schema_version": 9, "nodes": []}) is None
