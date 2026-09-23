"""S3 immutable revision persistence and deterministic TXT/PDF extraction."""

import hashlib
import re
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.connectors.s3 import S3Artifact
from app.models.source import SourceRevision
from app.pipelines.parsing import (
    MAX_CHUNKS,
    PARSER_VERSION,
    ProcessingError,
    pages,
    windows,
)
from app.pipelines.web_content import CLEANER_VERSION
from app.services.source_artifacts import (
    SourceArtifactSpec,
    config_hash,
    persist_source_artifact,
)


_SPACE = re.compile(r"\s+")


def processing_configuration(chunk, clean):
    value = {
        "extractor": PARSER_VERSION,
        "cleaner": CLEANER_VERSION,
        "clean": clean.model_dump(mode="json"),
        "chunk": chunk.model_dump(mode="json"),
    }
    return value, config_hash(value)


def _clean(value: str, clean) -> str:
    if clean.normalize_whitespace:
        value = _SPACE.sub(" ", value).strip()
    for repeated in clean.repeated_boilerplate:
        value = value.replace(repeated.strip(), " ")
    return _SPACE.sub(" ", value).strip()


def _chunks(path, media_type, source_key, chunk, clean, phase_callback=None):
    values = []
    extracted = []
    total_characters = 0
    clean_started = False
    chunk_started = False
    if phase_callback is not None:
        phase_callback("extract")
    for page_number, value, _, _ in pages(path, media_type):
        if phase_callback is not None and not clean_started:
            phase_callback("clean")
            clean_started = True
        cleaned = _clean(value, clean)
        if not cleaned:
            continue
        if phase_callback is not None and not chunk_started:
            phase_callback("chunk")
            chunk_started = True
        extracted.append(cleaned)
        for start, end, text in windows(cleaned, chunk.size, chunk.overlap):
            if len(values) >= MAX_CHUNKS:
                raise ProcessingError(
                    "S3 object exceeds the 50,000 chunk limit. Increase chunk size."
                )
            total_characters += len(text)
            if total_characters > 10_000_000:
                raise ProcessingError(
                    "S3 object exceeds the cleaned chunk-output limit."
                )
            values.append(
                {
                    "ordinal": len(values),
                    "page_number": page_number,
                    "start_char": start,
                    "end_char": end,
                    "text": text,
                    "provenance": {"s3_key": source_key},
                }
            )
    combined = "\n\n".join(extracted)
    if len(combined) < clean.minimum_text_chars:
        raise ProcessingError("S3 object contains too little extractable text.")
    if len(combined) > clean.maximum_text_chars:
        raise ProcessingError("S3 object exceeds the configured cleaned-text limit.")
    if not values:
        raise ProcessingError("S3 object contains no chunkable text.")
    return values, hashlib.sha256(combined.encode("utf-8")).hexdigest()


def persist_artifact(
    session: Session,
    project_id,
    connection_id,
    artifact: S3Artifact,
    chunk,
    clean,
    prior_revision: SourceRevision | None,
    phase_callback=None,
):
    if artifact.content is None or artifact.content_hash is None:
        raise ValueError("Changed S3 artifacts require fetched content.")
    metadata = artifact.item.metadata
    processing_config, processing_hash = processing_configuration(chunk, clean)
    media_type = artifact.item.media_type
    modified = artifact.item.modified_at

    def prepare(stored_path):
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
            parser_version=PARSER_VERSION,
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
    )
