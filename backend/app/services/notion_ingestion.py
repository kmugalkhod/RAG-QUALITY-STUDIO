"""Persist immutable Notion revisions with block-level chunk provenance."""

import hashlib

from sqlalchemy.orm import Session

from app.connectors.notion import NotionArtifact
from app.ingestion_content import (
    CharacterWindowChunker,
    ExtractedSegment,
    cleaner_for_node,
    processing_identity,
)
from app.models.source import SourceRevision
from app.pipelines.parsing import MAX_CHUNKS, PARSER_VERSION, ProcessingError
from app.pipelines.web_content import CLEANER_VERSION
from app.services.source_artifacts import (
    SourceArtifactSpec,
    config_hash,
    persist_source_artifact,
)


def processing_configuration(chunk, clean):
    if getattr(clean, "profile", None) is None:
        value = {
            "extractor": f"notion-blocks-{PARSER_VERSION}",
            "cleaner": CLEANER_VERSION,
            "clean": clean.model_dump(mode="json"),
            "chunk": chunk.model_dump(mode="json"),
        }
        return value, config_hash(value)
    cleaner = cleaner_for_node(clean)
    return processing_identity(
        schema_version=2 if getattr(clean, "profile", None) else 1,
        extractor_version=f"notion-blocks-{PARSER_VERSION}",
        cleaner_version=cleaner.version,
        chunker_version=CharacterWindowChunker.version,
        extract={"strategy": "notion_blocks"},
        clean=clean.model_dump(mode="json", exclude={"id", "type"}),
        chunk=chunk.model_dump(mode="json", exclude={"id", "type"}),
    )


def _chunks(artifact: NotionArtifact, chunk, clean, phase_callback=None):
    values = []
    extracted = []
    total = 0
    clean_started = False
    chunk_started = False
    if phase_callback is not None:
        phase_callback("extract")
    cleaner = cleaner_for_node(clean)
    chunker = CharacterWindowChunker()
    for segment in artifact.segments:
        if phase_callback is not None and not clean_started:
            phase_callback("clean")
            clean_started = True
        text = cleaner.clean(segment.text, clean)
        if not text:
            continue
        if phase_callback is not None and not chunk_started:
            phase_callback("chunk")
            chunk_started = True
        extracted.append(text)
        prepared_chunks = chunker.chunk_segment(
            ExtractedSegment(text=text),
            chunk,
            first_ordinal=len(values),
            provenance={
                "notion_page_id": artifact.item.external_id,
                "notion_block_id": segment.block_id,
                "notion_block_type": segment.block_type,
                "notion_block_depth": segment.depth,
                "section_path": list(segment.section_path),
            },
        )
        for prepared in prepared_chunks:
            if len(values) >= MAX_CHUNKS:
                raise ProcessingError(
                    "Notion page exceeds the 50,000 chunk limit. Increase chunk size."
                )
            total += len(prepared.text)
            if total > 10_000_000:
                raise ProcessingError("Notion page exceeds the chunk-output limit.")
            values.append(prepared.as_record())
    combined = "\n".join(extracted)
    length_violation = cleaner.length_violation(len(combined), clean)
    if length_violation == "too_short":
        raise ProcessingError("Notion page contains too little extractable text.")
    if length_violation == "too_long":
        raise ProcessingError("Notion page exceeds the configured cleaned-text limit.")
    if not values:
        raise ProcessingError("Notion page contains no chunkable text.")
    return values, hashlib.sha256(combined.encode()).hexdigest()


def persist_artifact(
    session: Session,
    project_id,
    connection_id,
    artifact: NotionArtifact,
    chunk,
    clean,
    prior_revision: SourceRevision | None,
    phase_callback=None,
):
    if artifact.content is None or artifact.content_hash is None:
        raise ValueError("Changed Notion artifacts require extracted content.")
    page_id = artifact.item.external_id
    metadata = artifact.item.metadata
    modified = artifact.item.modified_at
    processing_config, processing_hash = processing_configuration(chunk, clean)

    def prepare(_stored_path):
        return _chunks(artifact, chunk, clean, phase_callback)

    return persist_source_artifact(
        session,
        project_id,
        SourceArtifactSpec(
            kind="notion",
            identity=f"notion:{connection_id}:{page_id}",
            external_id=page_id,
            canonical_location=artifact.item.canonical_location,
            content=artifact.content,
            content_hash=artifact.content_hash,
            filename=f"{artifact.item.display_name[:251]}.txt",
            document_media_type="text/plain",
            revision_media_type="text/plain",
            processing_config=processing_config,
            processing_config_hash=processing_hash,
            parser_version=PARSER_VERSION,
            chunk_size=chunk.size,
            chunk_overlap=chunk.overlap,
            chunk_config_version=chunk.config_version,
            fetched_at=artifact.fetched_at,
            last_modified=modified.isoformat() if modified else None,
            provider_revision=artifact.item.provider_revision,
            provenance={
                "connector_kind": "notion",
                "connector_version": "1",
                "notion_api_version": "2026-03-11",
                "connection_id": str(connection_id),
                "page_id": page_id,
                "parent_type": metadata.get("parent_type"),
                "parent_id": metadata.get("parent_id"),
                "url": metadata.get("url"),
                "last_edited_time": metadata.get("last_edited_time"),
            },
        ),
        prior_revision,
        prepare,
    )
