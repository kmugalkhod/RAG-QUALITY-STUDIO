"""Persist immutable Confluence revisions with element/section provenance."""

import hashlib
import time
from app.connectors.confluence import ConfluenceArtifact
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
from app.ingestion_content.language import apply_language_policy
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
            "extractor": f"confluence-storage-{PARSER_VERSION}",
            "cleaner": CLEANER_VERSION,
            "clean": clean.model_dump(mode="json"),
            "chunk": chunk.model_dump(mode="json"),
        }
        return value, config_hash(value)
    cleaner = cleaner_for_node(clean)
    return processing_identity(
        schema_version=2 if getattr(clean, "profile", None) else 1,
        extractor_version=f"confluence-storage-{PARSER_VERSION}",
        cleaner_version=cleaner.version,
        chunker_version=chunker_version_for_node(chunk),
        extract={
            "strategy": "confluence_storage",
            "pipeline": (
                extract.model_dump(mode="json", exclude={"id", "type"})
                if extract is not None
                else None
            ),
        },
        clean=clean.model_dump(mode="json", exclude={"id", "type"}),
        chunk=chunk.model_dump(mode="json", exclude={"id", "type"}),
    )


def _chunks(artifact, chunk, clean, phase_callback=None):
    values, extracted, total = [], [], 0
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
                "confluence_page_id": artifact.item.external_id,
                "confluence_element": segment.element,
                "confluence_element_ordinal": segment.ordinal,
                "section_path": list(segment.section_path),
            },
        )
        for prepared in prepared_chunks:
            if len(values) >= MAX_CHUNKS:
                raise ProcessingError(
                    "Confluence page exceeds the 50,000 chunk limit. Increase chunk size."
                )
            total += len(prepared.text)
            if total > 10_000_000:
                raise ProcessingError("Confluence page exceeds the chunk-output limit.")
            values.append(prepared.as_record())
    combined = "\n".join(extracted)
    length_violation = cleaner.length_violation(len(combined), clean)
    if length_violation == "too_short":
        raise ProcessingError("Confluence page contains too little extractable text.")
    if length_violation == "too_long":
        raise ProcessingError(
            "Confluence page exceeds the configured cleaned-text limit."
        )
    if not values:
        raise ProcessingError("Confluence page contains no chunkable text.")
    return values, hashlib.sha256(combined.encode()).hexdigest()


def _block_type(element: str):
    if element.startswith("h") and element[1:].isdigit():
        return "heading"
    return {
        "p": "paragraph",
        "li": "list_item",
        "pre": "code",
        "blockquote": "quote",
        "td": "table",
        "th": "table",
    }.get(element, "unknown")


def _canonical_chunks(
    artifact,
    chunk,
    clean,
    processing_hash,
    phase_callback=None,
    extract=None,
    enforce_quality=True,
):
    if phase_callback is not None:
        phase_callback("extract")
    extractor_version = f"confluence-storage-{PARSER_VERSION}"
    extraction_started = time.perf_counter()
    extracted = build_extracted_document(
        [
            CanonicalInputSegment(
                text=segment.text,
                block_type=_block_type(segment.element),
                heading_path=segment.section_path,
                provider="confluence",
                external_id=f"{artifact.item.external_id}:{segment.ordinal}",
                attributes={"provider_element": segment.element},
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
        extracted = apply_language_policy(extracted, extract.language_policy)
        if enforce_quality and not quality_allows_publication(
            extract.quality_policy, extracted.measurements.quality_decision
        ):
            raise ProcessingError(
                "Confluence extraction did not satisfy the saved quality policy."
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
        raise ProcessingError("Confluence page contains too little extractable text.")
    if violation == "too_long":
        raise ProcessingError(
            "Confluence page exceeds the configured cleaned-text limit."
        )
    if phase_callback is not None:
        phase_callback("chunk")
    result = chunk_cleaned_document(
        cleaned,
        chunk,
        provenance={"confluence_page_id": artifact.item.external_id},
    )
    if not result.chunks:
        raise ProcessingError("Confluence page contains no chunkable text.")
    if len(result.chunks) > MAX_CHUNKS:
        raise ProcessingError(
            "Confluence page exceeds the 50,000 chunk limit. Increase chunk size."
        )
    if sum(len(item.text) for item in result.chunks) > 10_000_000:
        raise ProcessingError("Confluence page exceeds the chunk-output limit.")
    return PreparedArtifact(
        chunks=[item.as_record() for item in result.chunks],
        extracted_hash=hashlib.sha256(combined.encode()).hexdigest(),
        extracted=extracted,
        cleaned=cleaned,
        spans=result.spans,
        extractor_version=extractor_version,
    )


def persist_artifact(
    session,
    project_id,
    connection_id,
    artifact: ConfluenceArtifact,
    chunk,
    clean,
    prior_revision,
    phase_callback=None,
    extract=None,
):
    if artifact.content is None or artifact.content_hash is None:
        raise ValueError("Changed Confluence artifacts require extracted content.")
    page_id = artifact.item.external_id
    metadata = artifact.item.metadata
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
            kind="confluence",
            identity=f"confluence:{connection_id}:{page_id}",
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
            last_modified=metadata.get("version_created_at"),
            provider_revision=artifact.item.provider_revision,
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
