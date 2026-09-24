"""Persist immutable Notion revisions with block-level chunk provenance."""

import hashlib
import time

from sqlalchemy.orm import Session

from app.connectors.notion import NotionArtifact
from app.ingestion_content import (
    CanonicalInputSegment,
    CharacterWindowChunker,
    ExtractedSegment,
    build_extracted_document,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
    chunker_version_for_node,
    processing_identity,
)
from app.ingestion_content.quality import (
    evaluate_quality,
    measured_document,
    quality_allows_publication,
)
from app.models.source import SourceRevision
from app.pipelines.parsing import MAX_CHUNKS, PARSER_VERSION, ProcessingError
from app.pipelines.web_content import CLEANER_VERSION
from app.services.source_artifacts import (
    PreparedArtifact,
    SourceArtifactSpec,
    config_hash,
    persist_source_artifact,
)


def processing_configuration(chunk, clean, extract=None):
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
        chunker_version=chunker_version_for_node(chunk),
        extract={
            "strategy": "notion_blocks",
            "pipeline": (
                extract.model_dump(mode="json", exclude={"id", "type"})
                if extract is not None
                else None
            ),
        },
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


def _block_type(value: str):
    if value.startswith("heading_"):
        return "heading"
    if value in {"bulleted_list_item", "numbered_list_item", "to_do"}:
        return "list_item"
    if value in {"paragraph", "code", "quote", "table"}:
        return value
    return "unknown"


def _canonical_chunks(
    artifact: NotionArtifact,
    chunk,
    clean,
    processing_hash,
    phase_callback=None,
    extract=None,
    enforce_quality=True,
):
    if phase_callback is not None:
        phase_callback("extract")
    extractor_version = f"notion-blocks-{PARSER_VERSION}"
    extraction_started = time.perf_counter()
    extracted = build_extracted_document(
        [
            CanonicalInputSegment(
                text=segment.text,
                block_type=_block_type(segment.block_type),
                heading_path=segment.section_path,
                provider="notion",
                external_id=segment.block_id,
                attributes={
                    "provider_type": segment.block_type,
                    "depth": segment.depth,
                },
            )
            for segment in artifact.segments
        ],
        media_type="text/plain",
        title=artifact.item.display_name,
    )
    if extract is not None:
        extracted = measured_document(
            extracted,
            duration_ms=int((time.perf_counter() - extraction_started) * 1000),
        )
        extracted = evaluate_quality(extracted, extract.quality_policy)
        if enforce_quality and not quality_allows_publication(
            extract.quality_policy, extracted.measurements.quality_decision
        ):
            raise ProcessingError(
                "Notion extraction did not satisfy the saved quality policy."
            )
    if phase_callback is not None:
        phase_callback("clean")
    cleaner = cleaner_for_node(clean)
    cleaned = clean_document(
        extracted,
        clean,
        cleaner,
        extractor_version=extractor_version,
        configuration_hash=processing_hash,
    )
    combined = "\n".join(block.text for block in cleaned.blocks)
    violation = cleaner.length_violation(len(combined), clean)
    if violation == "too_short":
        raise ProcessingError("Notion page contains too little extractable text.")
    if violation == "too_long":
        raise ProcessingError("Notion page exceeds the configured cleaned-text limit.")
    if phase_callback is not None:
        phase_callback("chunk")
    result = chunk_cleaned_document(
        cleaned,
        chunk,
        provenance={"notion_page_id": artifact.item.external_id},
    )
    if not result.chunks:
        raise ProcessingError("Notion page contains no chunkable text.")
    if len(result.chunks) > MAX_CHUNKS:
        raise ProcessingError(
            "Notion page exceeds the 50,000 chunk limit. Increase chunk size."
        )
    if sum(len(item.text) for item in result.chunks) > 10_000_000:
        raise ProcessingError("Notion page exceeds the chunk-output limit.")
    return PreparedArtifact(
        chunks=[item.as_record() for item in result.chunks],
        extracted_hash=hashlib.sha256(combined.encode()).hexdigest(),
        extracted=extracted,
        cleaned=cleaned,
        spans=result.spans,
        extractor_version=extractor_version,
    )


def persist_artifact(
    session: Session,
    project_id,
    connection_id,
    artifact: NotionArtifact,
    chunk,
    clean,
    prior_revision: SourceRevision | None,
    phase_callback=None,
    extract=None,
):
    if artifact.content is None or artifact.content_hash is None:
        raise ValueError("Changed Notion artifacts require extracted content.")
    page_id = artifact.item.external_id
    metadata = artifact.item.metadata
    modified = artifact.item.modified_at
    processing_config, processing_hash = processing_configuration(chunk, clean, extract)

    def prepare(_stored_path):
        if getattr(clean, "profile", None) is not None:
            return _canonical_chunks(
                artifact, chunk, clean, processing_hash, phase_callback, extract
            )
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
        reuse_stage=phase_callback,
    )


def prepare_preview_artifact(artifact, chunk, clean, extract, processing_hash):
    return _canonical_chunks(
        artifact,
        chunk,
        clean,
        processing_hash,
        extract=extract,
        enforce_quality=False,
    )
