"""Website revision persistence and exact immutable-index preparation."""

import hashlib
import logging
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.connectors.website import WebsiteArtifact
from app.models.document import Chunk, Document, ProcessingRun
from app.models.source import SourceItem, SourceRevision, WebsiteRunItem
from app.pipelines.web_content import (
    CLEANER_VERSION,
    EXTRACTOR_VERSION,
    chunk_sections,
    extract_sections,
)
from app.services.source_artifacts import config_hash, identity_hash, store
from app.workers.processing import now


def _display_name(url: str) -> str:
    parts = urlsplit(url)
    tail = Path(parts.path).name or parts.hostname or "website"
    return tail[:255]


def persist_artifact(
    session: Session,
    project_id,
    artifact: WebsiteArtifact,
    chunk,
    clean,
    prior_revision: SourceRevision | None,
    phase_callback=None,
):
    source_item = session.scalar(
        select(SourceItem).where(
            SourceItem.project_id == project_id,
            SourceItem.kind == "website",
            SourceItem.identity_hash == identity_hash(artifact.canonical_location),
        )
    )
    if source_item is None:
        source_item = SourceItem(
            project_id=project_id,
            kind="website",
            external_id=artifact.canonical_location,
            identity_hash=identity_hash(artifact.canonical_location),
            canonical_location=artifact.canonical_location,
        )
        session.add(source_item)
        session.flush()
    else:
        source_item.canonical_location = artifact.canonical_location
        source_item.updated_at = now()

    content_hash = hashlib.sha256(artifact.content).hexdigest()
    processing_config = {
        "extractor": EXTRACTOR_VERSION,
        "cleaner": CLEANER_VERSION,
        "clean": clean.model_dump(mode="json"),
        "chunk": chunk.model_dump(mode="json"),
    }
    processing_hash = config_hash(processing_config)
    revision = session.scalar(
        select(SourceRevision).where(
            SourceRevision.source_item_id == source_item.id,
            SourceRevision.content_hash == content_hash,
            SourceRevision.processing_config_hash == processing_hash,
        )
    )
    if revision is not None:
        outcome = (
            "unchanged"
            if prior_revision is not None and revision.id == prior_revision.id
            else "changed"
        )
        return source_item, revision, outcome, revision.extracted_hash, None

    if phase_callback is not None:
        phase_callback("extract")
    sections = extract_sections(artifact.content, clean, phase_callback)
    extracted_hash = hashlib.sha256(
        "\n\n".join(section.text for section in sections).encode("utf-8")
    ).hexdigest()
    if phase_callback is not None:
        phase_callback("chunk")
    chunk_values = chunk_sections(sections, chunk.size, chunk.overlap)
    storage_name = None
    stored_path = None
    try:
        storage_name, stored_path = store(artifact.content)
        document = Document(
            project_id=project_id,
            filename=_display_name(artifact.canonical_location),
            storage_name=storage_name,
            media_type="text/html",
            content_hash=content_hash,
            size_bytes=len(artifact.content),
            origin_kind="website",
        )
        session.add(document)
        session.flush()
        processing = ProcessingRun(
            document_id=document.id,
            version=1,
            chunk_size=chunk.size,
            overlap=chunk.overlap,
            config_version=chunk.config_version,
            parser_version=f"{EXTRACTOR_VERSION}/{CLEANER_VERSION}",
            status="succeeded",
            attempts=1,
            progress=100,
            chunk_count=len(chunk_values),
            started_at=now(),
            finished_at=now(),
            updated_at=now(),
        )
        session.add(processing)
        session.flush()
        session.execute(
            insert(Chunk),
            [dict(run_id=processing.id, **value) for value in chunk_values],
        )
        revision = SourceRevision(
            project_id=project_id,
            source_item_id=source_item.id,
            document_id=document.id,
            processing_run_id=processing.id,
            content_hash=content_hash,
            extracted_hash=extracted_hash,
            processing_config_hash=processing_hash,
            media_type=artifact.media_type,
            size_bytes=len(artifact.content),
            artifact_storage_name=storage_name,
            etag=artifact.etag,
            last_modified=artifact.last_modified,
            provider_revision=artifact.etag or artifact.last_modified,
            fetched_at=now(),
            extraction_config=processing_config,
            provenance={
                "connector_kind": "website",
                "connector_version": "1",
                "canonical_location": artifact.canonical_location,
                "depth": artifact.depth,
            },
        )
        session.add(revision)
        session.flush()
    except Exception:
        if stored_path is not None:
            try:
                stored_path.unlink(missing_ok=True)
            except OSError:
                logging.warning(
                    "Website artifact cleanup unavailable; inspect offline."
                )
        raise
    return (
        source_item,
        revision,
        "new" if prior_revision is None else "changed",
        extracted_hash,
        stored_path,
    )


def add_run_item(
    session,
    *,
    run,
    ordinal,
    source_node_id,
    outcome,
    reason,
    location=None,
    display_name=None,
    media_type=None,
    source_item=None,
    revision=None,
    error=None,
):
    item = WebsiteRunItem(
        run_id=run.id,
        ordinal=ordinal,
        project_id=run.project_id,
        source_node_id=source_node_id,
        source_item_id=source_item.id if source_item else None,
        source_revision_id=revision.id if revision else None,
        canonical_location=location,
        display_name=(display_name or location or "Undiscovered website item")[:500],
        media_type=media_type,
        outcome=outcome,
        status="failed" if outcome == "failed" else "ready",
        reason=reason[:500],
        chunk_count=(
            session.get(ProcessingRun, revision.processing_run_id).chunk_count
            if revision
            else 0
        ),
        error=error,
        updated_at=now(),
    )
    session.add(item)
    return item


def require_artifacts(artifacts):
    if not artifacts:
        raise HTTPException(409, "Website discovery found no indexable HTML pages.")
