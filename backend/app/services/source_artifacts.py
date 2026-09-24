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

from pydantic import TypeAdapter
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Chunk, Document, ProcessingRun
from app.models.source import SourceItem, SourceRevision
from app.ingestion_content.contracts import (
    ChunkBlockSpanV1,
    CleanedDocumentV1,
    ExtractedDocumentV1,
)
from app.ingestion_content import chunk_cleaned_document, derivation_hash_from_config
from app.services.derivations import persist_derivations
from app.services.derivations import link_reused_derivations, reusable_cleaned_document
from app.schemas.ingestion import ChunkNodeV2
from app.pipelines.parsing import MAX_CHUNKS, ProcessingError


ChunkValues = list[dict[str, Any]]


@dataclass(frozen=True)
class PreparedArtifact:
    chunks: ChunkValues
    extracted_hash: str
    extracted: ExtractedDocumentV1
    cleaned: CleanedDocumentV1
    spans: dict[int, list[ChunkBlockSpanV1]]
    extractor_version: str


PrepareArtifact = Callable[[Path], tuple[ChunkValues, str] | PreparedArtifact]
ReuseStage = Callable[[str], None]


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


def reprocess_source_revision(
    session: Session,
    project_id: UUID,
    source_item: SourceItem,
    source_revision: SourceRevision,
    *,
    processing_config: dict[str, Any],
    processing_config_hash: str,
    parser_version: str,
    chunk_size: int,
    chunk_overlap: int,
    chunk_config_version: str,
    reuse_stage: ReuseStage | None = None,
) -> SourceRevision:
    """Create a chunk variant from a retained canonical derivation without refetching.

    Exact processing variants reuse the immutable revision. Changed variants are
    permitted only when the retained artifact has a compatible canonical cleaned
    derivation; extraction or cleaning changes require a connector refresh.
    """

    existing = session.scalar(
        select(SourceRevision).where(
            SourceRevision.source_item_id == source_item.id,
            SourceRevision.content_hash == source_revision.content_hash,
            SourceRevision.processing_config_hash == processing_config_hash,
        )
    )
    if existing is not None:
        return existing
    if processing_config.get("schema_version") != 2:
        raise ProcessingError(
            "Stored-artifact variants require a canonical v2 processing run. "
            "Refresh this connector with schema v2 before changing processing settings."
        )
    derivation_hash = derivation_hash_from_config(processing_config)
    reusable_revision = session.scalar(
        select(SourceRevision)
        .join(ProcessingRun, ProcessingRun.id == SourceRevision.processing_run_id)
        .where(
            SourceRevision.source_item_id == source_item.id,
            SourceRevision.content_hash == source_revision.content_hash,
            ProcessingRun.derivation_config_hash == derivation_hash,
            ProcessingRun.status == "succeeded",
        )
        .order_by(SourceRevision.created_at.desc(), SourceRevision.id.desc())
    )
    if reusable_revision is None:
        raise ProcessingError(
            "The retained source artifact has no compatible canonical derivation. "
            "Refresh the connector before changing extraction or cleaning settings."
        )
    if reuse_stage is not None:
        reuse_stage("chunk")
    cleaned, _ = reusable_cleaned_document(session, reusable_revision.processing_run_id)
    chunk_config = TypeAdapter(ChunkNodeV2).validate_python(
        {
            "id": "chunk",
            "type": "chunk",
            **(processing_config.get("chunk") or {}),
        }
    )
    provenance = {
        **(reusable_revision.provenance or {}),
        "processing_versions": processing_config.get("versions", {}),
        "reprocessed_from_source_revision_id": str(reusable_revision.id),
    }
    chunking = chunk_cleaned_document(
        cleaned,
        chunk_config,
        provenance=provenance,
        join_blocks=True,
    )
    if not chunking.chunks:
        raise ProcessingError("The retained source artifact has no chunkable text.")
    if len(chunking.chunks) > MAX_CHUNKS:
        raise ProcessingError(
            "The retained source artifact exceeds the 50,000 chunk limit."
        )
    if sum(len(item.text) for item in chunking.chunks) > 10_000_000:
        raise ProcessingError(
            "The retained source artifact exceeds the chunk-output limit."
        )
    values = [item.as_record() for item in chunking.chunks]
    encoded = json.dumps(
        values, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    output_hash = hashlib.sha256(encoded).hexdigest()
    source_run = session.get(ProcessingRun, reusable_revision.processing_run_id)
    document = session.get(Document, reusable_revision.document_id)
    if source_run is None or document is None or document.project_id != project_id:
        raise ProcessingError("The retained source artifact is no longer available.")
    next_version = (
        session.scalar(
            select(func.max(ProcessingRun.version)).where(
                ProcessingRun.document_id == document.id
            )
        )
        or 0
    ) + 1
    current_time = datetime.now(timezone.utc)
    processing = ProcessingRun(
        document_id=document.id,
        version=next_version,
        chunk_size=chunk_size,
        overlap=chunk_overlap,
        config_version=chunk_config_version,
        parser_version=parser_version,
        processing_config=processing_config,
        processing_config_hash=processing_config_hash,
        derivation_config_hash=derivation_hash,
        reused_from_processing_run_id=source_run.id,
        output_hash=output_hash,
        status="succeeded",
        attempts=1,
        progress=100,
        chunk_count=len(values),
        started_at=current_time,
        finished_at=current_time,
        updated_at=current_time,
    )
    session.add(processing)
    session.flush()
    session.execute(
        insert(Chunk), [dict(run_id=processing.id, **value) for value in values]
    )
    link_reused_derivations(
        session,
        processing_run_id=processing.id,
        source_processing_run_id=source_run.id,
        document_id=document.id,
        project_id=project_id,
        spans=chunking.spans,
    )
    revision = SourceRevision(
        project_id=project_id,
        source_item_id=source_item.id,
        document_id=document.id,
        processing_run_id=processing.id,
        content_hash=reusable_revision.content_hash,
        extracted_hash=reusable_revision.extracted_hash,
        processing_config_hash=processing_config_hash,
        media_type=reusable_revision.media_type,
        size_bytes=reusable_revision.size_bytes,
        artifact_storage_name=reusable_revision.artifact_storage_name,
        etag=reusable_revision.etag,
        last_modified=reusable_revision.last_modified,
        provider_revision=reusable_revision.provider_revision,
        fetched_at=reusable_revision.fetched_at,
        extraction_config=processing_config,
        provenance=provenance,
    )
    session.add(revision)
    session.flush()
    return revision


def persist_source_artifact(
    session: Session,
    project_id: UUID,
    spec: SourceArtifactSpec,
    prior_revision: SourceRevision | None,
    prepare: PrepareArtifact,
    reuse_stage: ReuseStage | None = None,
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

    derivation_hash = None
    if spec.processing_config.get("schema_version") == 2:
        derivation_hash = derivation_hash_from_config(spec.processing_config)
    reusable_revision = None
    if derivation_hash is not None:
        reusable_revision = session.scalar(
            select(SourceRevision)
            .join(
                ProcessingRun,
                ProcessingRun.id == SourceRevision.processing_run_id,
            )
            .where(
                SourceRevision.source_item_id == source_item.id,
                SourceRevision.content_hash == spec.content_hash,
                ProcessingRun.derivation_config_hash == derivation_hash,
                ProcessingRun.status == "succeeded",
            )
            .order_by(SourceRevision.created_at.desc(), SourceRevision.id.desc())
        )
    if reusable_revision is not None:
        if reuse_stage is not None:
            reuse_stage("chunk")
        cleaned, _ = reusable_cleaned_document(
            session, reusable_revision.processing_run_id
        )
        chunk_config = TypeAdapter(ChunkNodeV2).validate_python(
            {
                "id": "chunk",
                "type": "chunk",
                **(spec.processing_config.get("chunk") or {}),
            }
        )
        chunking = chunk_cleaned_document(
            cleaned,
            chunk_config,
            provenance={
                **spec.provenance,
                "processing_versions": spec.processing_config.get("versions", {}),
            },
            join_blocks=True,
        )
        if not chunking.chunks:
            raise ProcessingError("The reusable source snapshot has no chunkable text.")
        if len(chunking.chunks) > MAX_CHUNKS:
            raise ProcessingError(
                "The reusable source snapshot exceeds the 50,000 chunk limit."
            )
        if sum(len(item.text) for item in chunking.chunks) > 10_000_000:
            raise ProcessingError(
                "The reusable source snapshot exceeds the chunk-output limit."
            )
        values = [item.as_record() for item in chunking.chunks]
        encoded = json.dumps(
            values,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        output_hash = hashlib.sha256(encoded).hexdigest()
        source_run = session.get(ProcessingRun, reusable_revision.processing_run_id)
        document = session.get(Document, reusable_revision.document_id)
        if source_run is None or document is None or document.project_id != project_id:
            raise ValueError("The reusable source snapshot is no longer available.")
        next_version = (
            session.scalar(
                select(func.max(ProcessingRun.version)).where(
                    ProcessingRun.document_id == document.id
                )
            )
            or 0
        ) + 1
        processing = ProcessingRun(
            document_id=document.id,
            version=next_version,
            chunk_size=spec.chunk_size,
            overlap=spec.chunk_overlap,
            config_version=spec.chunk_config_version,
            parser_version=spec.parser_version,
            processing_config=spec.processing_config,
            processing_config_hash=spec.processing_config_hash,
            derivation_config_hash=derivation_hash,
            reused_from_processing_run_id=source_run.id,
            output_hash=output_hash,
            status="succeeded",
            attempts=1,
            progress=100,
            chunk_count=len(values),
            started_at=current_time,
            finished_at=current_time,
            updated_at=current_time,
        )
        session.add(processing)
        session.flush()
        session.execute(
            insert(Chunk),
            [dict(run_id=processing.id, **value) for value in values],
        )
        link_reused_derivations(
            session,
            processing_run_id=processing.id,
            source_processing_run_id=source_run.id,
            document_id=document.id,
            project_id=project_id,
            spans=chunking.spans,
        )
        revision = SourceRevision(
            project_id=project_id,
            source_item_id=source_item.id,
            document_id=document.id,
            processing_run_id=processing.id,
            content_hash=spec.content_hash,
            extracted_hash=reusable_revision.extracted_hash,
            processing_config_hash=spec.processing_config_hash,
            media_type=spec.revision_media_type,
            size_bytes=document.size_bytes,
            artifact_storage_name=reusable_revision.artifact_storage_name,
            etag=spec.etag,
            last_modified=spec.last_modified,
            provider_revision=spec.provider_revision,
            fetched_at=spec.fetched_at,
            extraction_config=spec.processing_config,
            provenance=spec.provenance,
        )
        session.add(revision)
        session.flush()
        return (
            source_item,
            revision,
            "new" if prior_revision is None else "changed",
            reusable_revision.extracted_hash,
            None,
        )

    stored_path: Path | None = None
    try:
        storage_name, stored_path = store(spec.content)
        prepared = prepare(stored_path)
        if isinstance(prepared, PreparedArtifact):
            chunk_values = prepared.chunks
            extracted_hash = prepared.extracted_hash
        else:
            chunk_values, extracted_hash = prepared
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
            processing_config=spec.processing_config,
            processing_config_hash=spec.processing_config_hash,
            derivation_config_hash=derivation_hash,
            output_hash=extracted_hash,
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
        if isinstance(prepared, PreparedArtifact):
            persist_derivations(
                session,
                project_id=project_id,
                document_id=document.id,
                processing_run_id=processing.id,
                extracted=prepared.extracted,
                cleaned=prepared.cleaned,
                extractor_version=prepared.extractor_version,
                spans=prepared.spans,
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
