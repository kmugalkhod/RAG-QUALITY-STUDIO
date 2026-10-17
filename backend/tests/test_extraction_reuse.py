"""Spec 0012 C5: a cleaning change reuses the extracted document, OCR included."""

from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion_content.cleaning import default_structure_steps
from app.models.derivation import ContentDerivation, ProcessingDerivation
from app.models.document import ProcessingRun
from app.models.ingestion import IngestionRunItem
from app.workers import processing as processing_worker
from test_documents import documents_api, upload  # noqa: F401
from test_existing_files_ingestion import (  # noqa: F401
    ingestion_api,
    ingestion_draft,
)

TEXT = (
    b"Harbour records\n\nThe archive keeps lanterns, maps and letters. "
    b"The survey collects infor-\nmation every year.\n\n" * 12
)


@pytest.fixture
def api(ingestion_api):  # noqa: F811
    return ingestion_api


def _start(client, project_id, version):
    response = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs"
    )
    assert response.status_code == 202, response.text
    return UUID(response.json()["id"])


def _processing(engine, run_id):
    with Session(engine) as session:
        return session.scalars(
            select(ProcessingRun)
            .join(
                IngestionRunItem, IngestionRunItem.processing_run_id == ProcessingRun.id
            )
            .where(IngestionRunItem.run_id == run_id)
        ).all()


def _draft(document_id, config, steps, duplicate=None):
    payload = ingestion_draft(
        [document_id], config, name="Reuse", schema_version=2, clean_steps=steps
    )
    if duplicate is not None:
        clean = next(n for n in payload["execution"]["nodes"] if n["type"] == "clean")
        clean["duplicate_policy"] = duplicate
    return payload


def test_a_cleaning_change_reuses_the_extracted_document(api, monkeypatch):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "reuse.txt")
    steps = deepcopy(default_structure_steps())
    first = client.post(
        f"/api/projects/{project_id}/pipelines",
        json=_draft(document["id"], config, steps),
    ).json()
    first_run = _start(client, project_id, first)
    [original] = _processing(engine, first_run)
    processing_worker.process(original.id, engine)
    # Only one run of an index may be active; the finished processing run stays.
    client.post(f"/api/projects/{project_id}/ingestion-runs/{first_run}/cancel")

    for step in steps:
        if step["type"] == "dehyphenate":
            step["enabled"] = False
    second = client.post(
        f"/api/projects/{project_id}/pipelines/{first['pipeline_id']}/versions",
        json=_draft(document["id"], config, steps),
    ).json()
    run_id = _start(client, project_id, second)
    [changed] = _processing(engine, run_id)
    assert changed.id != original.id
    assert changed.reused_from_processing_run_id is None
    assert changed.reused_extraction_from_processing_run_id == original.id

    def no_extraction(*_args, **_kwargs):
        raise AssertionError("The file was extracted again.")

    monkeypatch.setattr(processing_worker, "extract_document", no_extraction)
    processing_worker.process(changed.id, engine)
    with Session(engine) as session:
        run = session.get(ProcessingRun, changed.id)
        assert run.status == "succeeded", run.error
        derivations = dict(
            session.execute(
                select(ProcessingDerivation.kind, ContentDerivation)
                .join(
                    ContentDerivation,
                    ContentDerivation.id == ProcessingDerivation.derivation_id,
                )
                .where(ProcessingDerivation.processing_run_id == changed.id)
            ).all()
        )
        before = dict(
            session.execute(
                select(ProcessingDerivation.kind, ContentDerivation)
                .join(
                    ContentDerivation,
                    ContentDerivation.id == ProcessingDerivation.derivation_id,
                )
                .where(ProcessingDerivation.processing_run_id == original.id)
            ).all()
        )
    # The same extracted text; the cleaning change shows in the cleaned output.
    assert derivations["extracted"].output_hash == before["extracted"].output_hash
    assert derivations["cleaned"].output_hash != before["cleaned"].output_hash


def test_a_duplicate_policy_change_reuses_the_whole_processing_run(api):
    client, engine, project_id, _, config, _ = api
    document = upload(client, project_id, TEXT, "duplicate.txt")
    steps = deepcopy(default_structure_steps())
    first = client.post(
        f"/api/projects/{project_id}/pipelines",
        json=_draft(document["id"], config, steps),
    ).json()
    first_run = _start(client, project_id, first)
    [original] = _processing(engine, first_run)
    processing_worker.process(original.id, engine)
    # Only one run of an index may be active; the finished processing run stays.
    client.post(f"/api/projects/{project_id}/ingestion-runs/{first_run}/cancel")

    second = client.post(
        f"/api/projects/{project_id}/pipelines/{first['pipeline_id']}/versions",
        json=_draft(document["id"], config, steps, duplicate={"near_duplicate": True}),
    ).json()
    [reused] = _processing(engine, _start(client, project_id, second))
    assert reused.id == original.id


def test_the_migration_backfill_matches_the_application_hash():
    import importlib.util
    from pathlib import Path

    from app.ingestion_content import extraction_identity

    path = (
        Path(__file__).parents[1]
        / "migrations/versions/0052_processing_extraction_reuse.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0052", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    extract = {"strategy": "auto", "ocr": {"mode": "auto", "languages": ["eng"]}}
    config = {
        "schema_version": 2,
        "versions": {"extractor": "layout-ocr-v5", "cleaner": "x", "chunker": "y"},
        "extract": extract,
        "clean": {"profile": "structure-aware-v1"},
    }
    assert migration._extraction_hash(config) == extraction_identity(
        schema_version=2, extractor_version="layout-ocr-v5", extract=extract
    )
    assert migration._extraction_hash({**config, "schema_version": 1}) is None
