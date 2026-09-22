"""Persist immutable Confluence revisions with element/section provenance."""

import hashlib
import logging
import re

from sqlalchemy import insert, select

from app.connectors.confluence import ConfluenceArtifact
from app.models.document import Chunk, Document, ProcessingRun
from app.models.source import SourceItem, SourceRevision
from app.pipelines.parsing import MAX_CHUNKS, PARSER_VERSION, ProcessingError, windows
from app.pipelines.web_content import CLEANER_VERSION
from app.services.source_artifacts import config_hash, identity_hash, store
from app.workers.processing import now


_SPACE = re.compile(r"\s+")


def processing_configuration(chunk, clean):
    value = {
        "extractor": f"confluence-storage-{PARSER_VERSION}",
        "cleaner": CLEANER_VERSION,
        "clean": clean.model_dump(mode="json"),
        "chunk": chunk.model_dump(mode="json"),
    }
    return value, config_hash(value)


def _clean(value, clean):
    if clean.normalize_whitespace:
        value = _SPACE.sub(" ", value).strip()
    for repeated in clean.repeated_boilerplate:
        value = value.replace(repeated.strip(), " ")
    return _SPACE.sub(" ", value).strip()


def _chunks(artifact, chunk, clean, phase_callback=None):
    values, extracted, total = [], [], 0
    clean_started = False
    chunk_started = False
    if phase_callback is not None:
        phase_callback("extract")
    for segment in artifact.segments:
        if phase_callback is not None and not clean_started:
            phase_callback("clean")
            clean_started = True
        text = _clean(segment.text, clean)
        if not text:
            continue
        if phase_callback is not None and not chunk_started:
            phase_callback("chunk")
            chunk_started = True
        extracted.append(text)
        for start, end, value in windows(text, chunk.size, chunk.overlap):
            if len(values) >= MAX_CHUNKS:
                raise ProcessingError(
                    "Confluence page exceeds the 50,000 chunk limit. Increase chunk size."
                )
            total += len(value)
            if total > 10_000_000:
                raise ProcessingError("Confluence page exceeds the chunk-output limit.")
            values.append(
                {
                    "ordinal": len(values),
                    "page_number": None,
                    "start_char": start,
                    "end_char": end,
                    "text": value,
                    "provenance": {
                        "confluence_page_id": artifact.item.external_id,
                        "confluence_element": segment.element,
                        "confluence_element_ordinal": segment.ordinal,
                        "section_path": list(segment.section_path),
                    },
                }
            )
    combined = "\n".join(extracted)
    if len(combined) < clean.minimum_text_chars:
        raise ProcessingError("Confluence page contains too little extractable text.")
    if len(combined) > clean.maximum_text_chars:
        raise ProcessingError(
            "Confluence page exceeds the configured cleaned-text limit."
        )
    if not values:
        raise ProcessingError("Confluence page contains no chunkable text.")
    return values, hashlib.sha256(combined.encode()).hexdigest()


def persist_artifact(
    session,
    project_id,
    connection_id,
    artifact: ConfluenceArtifact,
    chunk,
    clean,
    prior_revision,
    phase_callback=None,
):
    if artifact.content is None or artifact.content_hash is None:
        raise ValueError("Changed Confluence artifacts require extracted content.")
    page_id = artifact.item.external_id
    identity = f"confluence:{connection_id}:{page_id}"
    source_item = session.scalar(
        select(SourceItem).where(
            SourceItem.project_id == project_id,
            SourceItem.kind == "confluence",
            SourceItem.identity_hash == identity_hash(identity),
        )
    )
    if source_item is None:
        source_item = SourceItem(
            project_id=project_id,
            kind="confluence",
            external_id=page_id,
            identity_hash=identity_hash(identity),
            canonical_location=artifact.item.canonical_location,
        )
        session.add(source_item)
        session.flush()
    else:
        source_item.canonical_location = artifact.item.canonical_location
        source_item.updated_at = now()
    processing_config, processing_hash = processing_configuration(chunk, clean)
    revision = session.scalar(
        select(SourceRevision).where(
            SourceRevision.source_item_id == source_item.id,
            SourceRevision.content_hash == artifact.content_hash,
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
    storage_name = stored_path = None
    try:
        storage_name, stored_path = store(artifact.content)
        chunk_values, extracted_hash = _chunks(artifact, chunk, clean, phase_callback)
        document = Document(
            project_id=project_id,
            filename=f"{artifact.item.display_name[:251]}.txt",
            storage_name=storage_name,
            media_type="text/plain",
            content_hash=artifact.content_hash,
            size_bytes=len(artifact.content),
            origin_kind="confluence",
        )
        session.add(document)
        session.flush()
        processing = ProcessingRun(
            document_id=document.id,
            version=1,
            chunk_size=chunk.size,
            overlap=chunk.overlap,
            config_version=chunk.config_version,
            parser_version=PARSER_VERSION,
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
        metadata = artifact.item.metadata
        revision = SourceRevision(
            project_id=project_id,
            source_item_id=source_item.id,
            document_id=document.id,
            processing_run_id=processing.id,
            content_hash=artifact.content_hash,
            extracted_hash=extracted_hash,
            processing_config_hash=processing_hash,
            media_type="text/plain",
            size_bytes=len(artifact.content),
            artifact_storage_name=storage_name,
            etag=None,
            last_modified=metadata.get("version_created_at"),
            provider_revision=artifact.item.provider_revision,
            fetched_at=artifact.fetched_at,
            extraction_config=processing_config,
            provenance={
                "connector_kind": "confluence",
                "connector_version": "1",
                "confluence_api_version": "2",
                "connection_id": str(connection_id),
                "page_id": page_id,
                "space_id": metadata.get("space_id"),
                "parent_id": metadata.get("parent_id"),
                "parent_type": metadata.get("parent_type"),
                "status": metadata.get("status"),
                "version": metadata.get("version"),
                "version_created_at": metadata.get("version_created_at"),
                "web_url": metadata.get("web_url"),
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
                    "Confluence artifact cleanup unavailable; inspect offline."
                )
        raise
    return (
        source_item,
        revision,
        "new" if prior_revision is None else "changed",
        extracted_hash,
        stored_path,
    )
