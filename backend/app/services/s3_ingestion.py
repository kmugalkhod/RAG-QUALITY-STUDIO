"""S3 immutable revision persistence and deterministic TXT/PDF extraction."""

import hashlib
import logging
import re
from pathlib import PurePosixPath

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.connectors.s3 import S3Artifact
from app.models.document import Chunk, Document, ProcessingRun
from app.models.source import SourceItem, SourceRevision
from app.pipelines.parsing import (
    MAX_CHUNKS,
    PARSER_VERSION,
    ProcessingError,
    pages,
    windows,
)
from app.pipelines.web_content import CLEANER_VERSION
from app.services.source_artifacts import config_hash, identity_hash, store
from app.workers.processing import now


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


def _chunks(path, media_type, source_key, chunk, clean):
    values = []
    extracted = []
    total_characters = 0
    for page_number, value, _, _ in pages(path, media_type):
        cleaned = _clean(value, clean)
        if not cleaned:
            continue
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
):
    if artifact.content is None or artifact.content_hash is None:
        raise ValueError("Changed S3 artifacts require fetched content.")
    metadata = artifact.item.metadata
    identity = f"s3:{connection_id}:{metadata['bucket']}:{metadata['key']}"
    source_item = session.scalar(
        select(SourceItem).where(
            SourceItem.project_id == project_id,
            SourceItem.kind == "s3",
            SourceItem.identity_hash == identity_hash(identity),
        )
    )
    if source_item is None:
        source_item = SourceItem(
            project_id=project_id,
            kind="s3",
            external_id=str(metadata["key"]),
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

    storage_name = None
    stored_path = None
    try:
        storage_name, stored_path = store(artifact.content)
        media_type = artifact.item.media_type
        chunk_values, extracted_hash = _chunks(
            stored_path, media_type, str(metadata["key"]), chunk, clean
        )
        filename = (PurePosixPath(str(metadata["key"])).name or "s3-object")[:255]
        document = Document(
            project_id=project_id,
            filename=filename,
            storage_name=storage_name,
            media_type=media_type,
            content_hash=artifact.content_hash,
            size_bytes=len(artifact.content),
            origin_kind="s3",
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
        modified = artifact.item.modified_at
        revision = SourceRevision(
            project_id=project_id,
            source_item_id=source_item.id,
            document_id=document.id,
            processing_run_id=processing.id,
            content_hash=artifact.content_hash,
            extracted_hash=extracted_hash,
            processing_config_hash=processing_hash,
            media_type=media_type,
            size_bytes=len(artifact.content),
            artifact_storage_name=storage_name,
            etag=str(metadata.get("etag") or "") or None,
            last_modified=modified.isoformat() if modified else None,
            provider_revision=artifact.item.provider_revision,
            fetched_at=artifact.fetched_at,
            extraction_config=processing_config,
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
        )
        session.add(revision)
        session.flush()
    except Exception:
        if stored_path is not None:
            try:
                stored_path.unlink(missing_ok=True)
            except OSError:
                logging.warning("S3 artifact cleanup unavailable; inspect offline.")
        raise
    return (
        source_item,
        revision,
        "new" if prior_revision is None else "changed",
        extracted_hash,
        stored_path,
    )
