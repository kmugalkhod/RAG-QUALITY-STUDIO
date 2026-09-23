"""Shared immutable artifact storage and deterministic identity helpers."""

import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID
from uuid import uuid4

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Chunk, Document, ProcessingRun
from app.models.source import SourceItem, SourceRevision


ChunkValues = list[dict[str, Any]]
PrepareArtifact = Callable[[Path], tuple[ChunkValues, str]]


@dataclass(frozen=True)
class SourceArtifactSpec:
    """Connector-owned facts needed to persist one immutable source revision."""

    kind: str
    identity: str
    external_id: str
    canonical_location: str
    content: bytes
    content_hash: str
    filename: str
    document_media_type: str
    revision_media_type: str
    processing_config: dict[str, Any]
    processing_config_hash: str
    parser_version: str
    chunk_size: int
    chunk_overlap: int
    chunk_config_version: str
    fetched_at: datetime
    provenance: dict[str, Any]
    etag: str | None = None
    last_modified: str | None = None
    provider_revision: str | None = None


def store(content: bytes) -> tuple[str, Path]:
    root = settings.storage_path
    root.mkdir(parents=True, exist_ok=True)
    name = uuid4().hex
    temporary = root / f"{name}.part"
    final = root / name
    with temporary.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, final)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return name, final


def identity_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def config_hash(value: dict) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def persist_source_artifact(
    session: Session,
    project_id: UUID,
    spec: SourceArtifactSpec,
    prior_revision: SourceRevision | None,
    prepare: PrepareArtifact,
) -> tuple[SourceItem, SourceRevision, str, str, Path | None]:
    """Reuse or atomically stage one connector artifact and its derived chunks.

    The caller owns the transaction. This boundary owns the repeated source identity,
    immutable-revision lookup, document/run/chunk rows, and best-effort file cleanup.
    Connector callbacks retain extraction, validation, and provenance semantics.
    """

    current_time = datetime.now(timezone.utc)
    item_hash = identity_hash(spec.identity)
    source_item = session.scalar(
        select(SourceItem).where(
            SourceItem.project_id == project_id,
            SourceItem.kind == spec.kind,
            SourceItem.identity_hash == item_hash,
        )
    )
    if source_item is None:
        source_item = SourceItem(
            project_id=project_id,
            kind=spec.kind,
            external_id=spec.external_id,
            identity_hash=item_hash,
            canonical_location=spec.canonical_location,
        )
        session.add(source_item)
        session.flush()
    else:
        source_item.canonical_location = spec.canonical_location
        source_item.updated_at = current_time

    revision = session.scalar(
        select(SourceRevision).where(
            SourceRevision.source_item_id == source_item.id,
            SourceRevision.content_hash == spec.content_hash,
            SourceRevision.processing_config_hash == spec.processing_config_hash,
        )
    )
    if revision is not None:
        outcome = (
            "unchanged"
            if prior_revision is not None and revision.id == prior_revision.id
            else "changed"
        )
        return source_item, revision, outcome, revision.extracted_hash, None

    stored_path: Path | None = None
    try:
        storage_name, stored_path = store(spec.content)
        chunk_values, extracted_hash = prepare(stored_path)
        document = Document(
            project_id=project_id,
            filename=spec.filename,
            storage_name=storage_name,
            media_type=spec.document_media_type,
            content_hash=spec.content_hash,
            size_bytes=len(spec.content),
            origin_kind=spec.kind,
        )
        session.add(document)
        session.flush()
        processing = ProcessingRun(
            document_id=document.id,
            version=1,
            chunk_size=spec.chunk_size,
            overlap=spec.chunk_overlap,
            config_version=spec.chunk_config_version,
            parser_version=spec.parser_version,
            status="succeeded",
            attempts=1,
            progress=100,
            chunk_count=len(chunk_values),
            started_at=current_time,
            finished_at=current_time,
            updated_at=current_time,
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
            content_hash=spec.content_hash,
            extracted_hash=extracted_hash,
            processing_config_hash=spec.processing_config_hash,
            media_type=spec.revision_media_type,
            size_bytes=len(spec.content),
            artifact_storage_name=storage_name,
            etag=spec.etag,
            last_modified=spec.last_modified,
            provider_revision=spec.provider_revision,
            fetched_at=spec.fetched_at,
            extraction_config=spec.processing_config,
            provenance=spec.provenance,
        )
        session.add(revision)
        session.flush()
    except Exception:
        if stored_path is not None:
            try:
                stored_path.unlink(missing_ok=True)
            except OSError:
                logging.warning(
                    "%s artifact cleanup unavailable; inspect offline.",
                    spec.kind.capitalize(),
                )
        raise

    return (
        source_item,
        revision,
        "new" if prior_revision is None else "changed",
        extracted_hash,
        stored_path,
    )
