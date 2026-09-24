"""S3 immutable revision persistence and deterministic TXT/PDF extraction."""

import hashlib
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.connectors.s3 import S3Artifact
from app.ingestion_content import (
    CharacterWindowChunker,
    ExtractedSegment,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
    chunker_version_for_node,
    processing_identity,
)
from app.ingestion_content.extractors import (
    extract_document,
    extractor_version_for_settings,
)
from app.ingestion_content.quality import quality_allows_publication
from app.schemas.ingestion import ExtractNodeV2
from app.models.source import SourceRevision
from app.pipelines.parsing import (
    MAX_CHUNKS,
    PARSER_VERSION,
    ProcessingError,
    pages,
)
from app.pipelines.web_content import CLEANER_VERSION
from app.services.source_artifacts import (
    PreparedArtifact,
    SourceArtifactSpec,
    config_hash,
    persist_source_artifact,
)


def _extract_settings(extract=None):
    return extract or ExtractNodeV2(id="extract", type="extract")


def processing_configuration(chunk, clean, extract=None):
    if getattr(clean, "profile", None) is None:
        value = {
            "extractor": PARSER_VERSION,
            "cleaner": CLEANER_VERSION,
            "clean": clean.model_dump(mode="json"),
            "chunk": chunk.model_dump(mode="json"),
        }
        return value, config_hash(value)
    cleaner = cleaner_for_node(clean)
    extract = _extract_settings(extract)
    return processing_identity(
        schema_version=2 if getattr(clean, "profile", None) else 1,
        extractor_version=extractor_version_for_settings(extract),
        cleaner_version=cleaner.version,
        chunker_version=chunker_version_for_node(chunk),
        extract=extract.model_dump(mode="json", exclude={"id", "type"}),
        clean=clean.model_dump(mode="json", exclude={"id", "type"}),
        chunk=chunk.model_dump(mode="json", exclude={"id", "type"}),
    )


def _chunks(path, media_type, source_key, chunk, clean, phase_callback=None):
    values = []
    extracted = []
    total_characters = 0
    clean_started = False
    chunk_started = False
    if phase_callback is not None:
        phase_callback("extract")
    cleaner = cleaner_for_node(clean)
    chunker = CharacterWindowChunker()
    for page_number, value, _, _ in pages(path, media_type):
        if phase_callback is not None and not clean_started:
            phase_callback("clean")
            clean_started = True
        cleaned = cleaner.clean(value, clean)
        if not cleaned:
            continue
        if phase_callback is not None and not chunk_started:
            phase_callback("chunk")
            chunk_started = True
        extracted.append(cleaned)
        chunks = chunker.chunk_segment(
            ExtractedSegment(text=cleaned, page_number=page_number),
            chunk,
            first_ordinal=len(values),
            provenance={"s3_key": source_key},
        )
        for prepared in chunks:
            if len(values) >= MAX_CHUNKS:
                raise ProcessingError(
                    "S3 object exceeds the 50,000 chunk limit. Increase chunk size."
                )
            total_characters += len(prepared.text)
            if total_characters > 10_000_000:
                raise ProcessingError(
                    "S3 object exceeds the cleaned chunk-output limit."
                )
            values.append(prepared.as_record())
    combined = "\n\n".join(extracted)
    length_violation = cleaner.length_violation(len(combined), clean)
    if length_violation == "too_short":
        raise ProcessingError("S3 object contains too little extractable text.")
    if length_violation == "too_long":
        raise ProcessingError("S3 object exceeds the configured cleaned-text limit.")
    if not values:
        raise ProcessingError("S3 object contains no chunkable text.")
    return values, hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _canonical_chunks(
    path,
    media_type,
    source_key,
    title,
    chunk,
    clean,
    processing_hash,
    phase_callback=None,
    extract=None,
    enforce_quality=True,
):
    if phase_callback is not None:
        phase_callback("extract")
    extract = _extract_settings(extract)
    extracted, extractor_version = extract_document(path, media_type, title, extract)
    if enforce_quality and not quality_allows_publication(
        extract.quality_policy, extracted.measurements.quality_decision
    ):
        raise ProcessingError("S3 extraction did not satisfy the saved quality policy.")
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
    violation = cleaner.length_violation(cleaned.measurements.character_count, clean)
    if violation == "too_short":
        raise ProcessingError("S3 object contains too little extractable text.")
    if violation == "too_long":
        raise ProcessingError("S3 object exceeds the configured cleaned-text limit.")
    if phase_callback is not None:
        phase_callback("chunk")
    result = chunk_cleaned_document(cleaned, chunk, provenance={"s3_key": source_key})
    if not result.chunks:
        raise ProcessingError("S3 object contains no chunkable text.")
    if len(result.chunks) > MAX_CHUNKS:
        raise ProcessingError(
            "S3 object exceeds the 50,000 chunk limit. Increase chunk size."
        )
    if sum(len(item.text) for item in result.chunks) > 10_000_000:
        raise ProcessingError("S3 object exceeds the cleaned chunk-output limit.")
    combined_hash = hashlib.sha256(
        "\n\n".join(block.text for block in cleaned.blocks).encode("utf-8")
    ).hexdigest()
    return PreparedArtifact(
        chunks=[item.as_record() for item in result.chunks],
        extracted_hash=combined_hash,
        extracted=extracted,
        cleaned=cleaned,
        spans=result.spans,
        extractor_version=extractor_version,
    )


def prepare_preview_artifact(
    path, media_type, source_key, title, chunk, clean, extract, processing_hash
):
    return _canonical_chunks(
        path,
        media_type,
        source_key,
        title,
        chunk,
        clean,
        processing_hash,
        extract=extract,
        enforce_quality=False,
    )


def persist_artifact(
    session: Session,
    project_id,
    connection_id,
    artifact: S3Artifact,
    chunk,
    clean,
    prior_revision: SourceRevision | None,
    phase_callback=None,
    extract=None,
):
    if artifact.content is None or artifact.content_hash is None:
        raise ValueError("Changed S3 artifacts require fetched content.")
    metadata = artifact.item.metadata
    processing_config, processing_hash = processing_configuration(chunk, clean, extract)
    media_type = artifact.item.media_type
    modified = artifact.item.modified_at

    def prepare(stored_path):
        if getattr(clean, "profile", None) is not None:
            return _canonical_chunks(
                stored_path,
                media_type,
                str(metadata["key"]),
                PurePosixPath(str(metadata["key"])).name or "s3-object",
                chunk,
                clean,
                processing_hash,
                phase_callback,
                extract,
            )
        return _chunks(
            stored_path,
            media_type,
            str(metadata["key"]),
            chunk,
            clean,
            phase_callback,
        )

    return persist_source_artifact(
        session,
        project_id,
        SourceArtifactSpec(
            kind="s3",
            identity=f"s3:{connection_id}:{metadata['bucket']}:{metadata['key']}",
            external_id=str(metadata["key"]),
            canonical_location=artifact.item.canonical_location,
            content=artifact.content,
            content_hash=artifact.content_hash,
            filename=(PurePosixPath(str(metadata["key"])).name or "s3-object")[:255],
            document_media_type=media_type,
            revision_media_type=media_type,
            processing_config=processing_config,
            processing_config_hash=processing_hash,
            parser_version=(
                extractor_version_for_settings(_extract_settings(extract))
                if getattr(clean, "profile", None) is not None
                else PARSER_VERSION
            ),
            chunk_size=chunk.size,
            chunk_overlap=chunk.overlap,
            chunk_config_version=chunk.config_version,
            fetched_at=artifact.fetched_at,
            etag=str(metadata.get("etag") or "") or None,
            last_modified=modified.isoformat() if modified else None,
            provider_revision=artifact.item.provider_revision,
            provenance={
                "connector_kind": "s3",
                "connector_version": "1",
                "connection_id": str(connection_id),
                "bucket": metadata["bucket"],
                "key": metadata["key"],
                "version_id": metadata.get("version_id"),
                "etag": metadata.get("etag"),
                "size_bytes": metadata["size_bytes"],
                "last_modified": modified.isoformat() if modified else None,
            },
        ),
        prior_revision,
        prepare,
        reuse_stage=phase_callback,
    )
