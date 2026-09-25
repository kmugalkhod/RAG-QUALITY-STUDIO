"""Persistence and project-scoped reads for immutable content derivations."""

from __future__ import annotations

from uuid import UUID
from math import ceil
from statistics import median

from fastapi import HTTPException
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.ingestion_content.contracts import (
    CanonicalBlock,
    CleanedDocumentV1,
    ExtractedDocumentV1,
    ChunkBlockSpanV1,
)
from app.models.derivation import (
    ChunkBlockSpan,
    ContentBlock,
    ContentDerivation,
    ProcessingDerivation,
)
from app.models.document import Chunk, Document, ProcessingRun
from app.core.config import settings
from app.ingestion_content.processing import IngestionStageError
from app.ingestion_content.extractors import render_pdf_thumbnail
from app.services import artifact_storage
from app.core.artifact_crypto import (
    ArtifactConfigurationError,
    ArtifactKeyring,
    ArtifactUnavailableError,
)
from app.core.auth import Principal, authorize_sensitive_read, project_role
from app.schemas.derivation import ContentDerivationRead


def _protected_derivation_key(
    session: Session, derivation: ContentDerivation
) -> tuple[ArtifactKeyring, bytes]:
    document = session.scalar(
        select(Document).where(
            Document.id == derivation.document_id,
            Document.project_id == derivation.project_id,
        )
    )
    if document is None or document.artifact_state != "encrypted":
        raise HTTPException(410, "The retained protected source is unavailable.")
    try:
        keyring = ArtifactKeyring.from_settings(settings)
        data_key = keyring.unwrap_key(
            wrapped_key=document.artifact_wrapped_key,
            wrap_nonce=document.artifact_wrap_nonce,
            key_version=document.artifact_key_version,
            schema_version=document.artifact_encryption_schema,
            project_id=derivation.project_id,
            document_id=derivation.document_id,
        )
        return keyring, data_key
    except (ArtifactConfigurationError, ArtifactUnavailableError):
        raise HTTPException(503, "Protected source text is unavailable.") from None


def _block_text(
    block: ContentBlock,
    derivation: ContentDerivation,
    keyring: ArtifactKeyring | None,
    data_key: bytes | None,
) -> str:
    if block.protected_text_ciphertext is None:
        return block.text
    if keyring is None or data_key is None or block.protected_text_nonce is None:
        raise HTTPException(503, "Protected source text is unavailable.")
    try:
        return keyring.decrypt_protected_text(
            data_key,
            block.protected_text_ciphertext,
            block.protected_text_nonce,
            project_id=derivation.project_id,
            document_id=derivation.document_id,
            context=f"derivation:{derivation.id}:block:{block.ordinal}",
        )
    except ArtifactUnavailableError:
        raise HTTPException(503, "Protected source text is unavailable.") from None


def _derivation_values(
    document,
    kind: str,
    *,
    project_id: UUID,
    document_id: UUID,
    processing_run_id: UUID,
    engine_version: str,
    hashes: dict,
):
    return dict(
        project_id=project_id,
        document_id=document_id,
        processing_run_id=processing_run_id,
        kind=kind,
        schema_version=1,
        engine_version=engine_version,
        configuration_hash=hashes["configuration_hash"],
        input_hash=hashes["input_hash"],
        output_hash=hashes["output_hash"],
        title=document.title,
        media_type=document.media_type,
        language=(
            document.language.model_dump(mode="json") if document.language else None
        ),
        measurements=document.measurements.model_dump(mode="json"),
        findings=[item.model_dump(mode="json") for item in document.findings],
        sensitive_findings=(
            [item.model_dump(mode="json") for item in document.sensitive_findings]
            if isinstance(document, CleanedDocumentV1)
            else []
        ),
        sensitive_data_applied=(
            document.sensitive_data_applied
            if isinstance(document, CleanedDocumentV1)
            else False
        ),
        protected_text=False,
        transforms=(
            [item.model_dump(mode="json") for item in document.transforms]
            if isinstance(document, CleanedDocumentV1)
            else []
        ),
    )


def _persist_blocks(
    session: Session,
    derivation_id: UUID,
    document: ExtractedDocumentV1 | CleanedDocumentV1,
    *,
    protect_text: bool = False,
    project_id: UUID | None = None,
    document_id: UUID | None = None,
    keyring: ArtifactKeyring | None = None,
    data_key: bytes | None = None,
):
    values = []
    for block in document.blocks:
        ciphertext = None
        nonce = None
        text = block.text
        if protect_text:
            if (
                project_id is None
                or document_id is None
                or keyring is None
                or data_key is None
            ):
                raise ValueError("Protected derivation encryption is unavailable.")
            ciphertext, nonce = keyring.encrypt_protected_text(
                data_key,
                block.text,
                project_id=project_id,
                document_id=document_id,
                context=f"derivation:{derivation_id}:block:{block.ordinal}",
            )
            text = "[PROTECTED SOURCE TEXT]"
        values.append(
            dict(
                derivation_id=derivation_id,
                ordinal=block.ordinal,
                block_id=block.id,
                block_type=block.type,
                text=text,
                protected_text_ciphertext=ciphertext,
                protected_text_nonce=nonce,
                page_number=block.page_number,
                bounding_box=(
                    block.bounding_box.model_dump(mode="json")
                    if block.bounding_box
                    else None
                ),
                heading_path=block.heading_path,
                source_span=block.source_span.model_dump(mode="json"),
                attributes=block.attributes,
            )
        )
    for start in range(0, len(values), 500):
        session.execute(insert(ContentBlock), values[start : start + 500])


def persist_derivations(
    session: Session,
    *,
    project_id: UUID,
    document_id: UUID,
    processing_run_id: UUID,
    extracted: ExtractedDocumentV1,
    cleaned: CleanedDocumentV1,
    extractor_version: str,
    spans: dict[int, list[ChunkBlockSpanV1]],
) -> tuple[ContentDerivation, ContentDerivation]:
    """Persist extracted/cleaned IR and chunk spans inside the caller transaction."""

    if session.scalar(
        select(ContentDerivation.id).where(
            ContentDerivation.processing_run_id == processing_run_id
        )
    ):
        raise ValueError("Canonical derivations already exist for this processing run.")
    document = session.scalar(
        select(Document).where(
            Document.id == document_id, Document.project_id == project_id
        )
    )
    run = session.scalar(
        select(ProcessingRun).where(
            ProcessingRun.id == processing_run_id,
            ProcessingRun.document_id == document_id,
        )
    )
    if document is None or run is None:
        raise ValueError("Processing ownership is invalid for canonical persistence.")

    protect_extracted = cleaned.sensitive_data_applied
    keyring = None
    data_key = None
    if protect_extracted:
        if document.artifact_state != "encrypted":
            raise IngestionStageError(
                "clean",
                "raw_artifact_encryption_required",
                "Sensitive-data processing requires encrypted raw-artifact storage.",
            )
        keyring = ArtifactKeyring.from_settings(settings)
        data_key = keyring.unwrap_key(
            wrapped_key=document.artifact_wrapped_key,
            wrap_nonce=document.artifact_wrap_nonce,
            key_version=document.artifact_key_version,
            schema_version=document.artifact_encryption_schema,
            project_id=project_id,
            document_id=document_id,
        )
    extracted_hash = cleaned.input_hash
    extracted_row = ContentDerivation(
        **_derivation_values(
            extracted,
            "extracted",
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            engine_version=extractor_version,
            hashes={
                "configuration_hash": cleaned.configuration_hash,
                "input_hash": extracted_hash,
                "output_hash": extracted_hash,
            },
        )
    )
    cleaned_row = ContentDerivation(
        **_derivation_values(
            cleaned,
            "cleaned",
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            engine_version=cleaned.cleaner_version,
            hashes={
                "configuration_hash": cleaned.configuration_hash,
                "input_hash": cleaned.input_hash,
                "output_hash": cleaned.output_hash,
            },
        )
    )
    extracted_row.protected_text = protect_extracted
    session.add_all([extracted_row, cleaned_row])
    session.flush()
    _persist_blocks(
        session,
        extracted_row.id,
        extracted,
        protect_text=protect_extracted,
        project_id=project_id,
        document_id=document_id,
        keyring=keyring,
        data_key=data_key,
    )
    _persist_blocks(session, cleaned_row.id, cleaned)

    session.add_all(
        [
            ProcessingDerivation(
                processing_run_id=processing_run_id,
                kind="extracted",
                derivation_id=extracted_row.id,
                document_id=document_id,
                project_id=project_id,
                reused=False,
            ),
            ProcessingDerivation(
                processing_run_id=processing_run_id,
                kind="cleaned",
                derivation_id=cleaned_row.id,
                document_id=document_id,
                project_id=project_id,
                reused=False,
            ),
        ]
    )
    session.flush()

    _persist_spans(session, processing_run_id, cleaned_row.id, spans)
    return extracted_row, cleaned_row


def _persist_spans(
    session: Session,
    processing_run_id: UUID,
    cleaned_derivation_id: UUID,
    spans: dict[int, list[ChunkBlockSpanV1]],
):
    span_values = []
    for chunk_ordinal, chunk_spans in spans.items():
        for span_ordinal, span in enumerate(chunk_spans):
            span_values.append(
                dict(
                    run_id=processing_run_id,
                    chunk_ordinal=chunk_ordinal,
                    span_ordinal=span_ordinal,
                    derivation_id=cleaned_derivation_id,
                    derivation_kind="cleaned",
                    block_ordinal=span.block_ordinal,
                    block_start_char=span.block_start_char,
                    block_end_char=span.block_end_char,
                    chunk_start_char=span.chunk_start_char,
                    chunk_end_char=span.chunk_end_char,
                )
            )
    for start in range(0, len(span_values), 500):
        session.execute(insert(ChunkBlockSpan), span_values[start : start + 500])


def reusable_cleaned_document(
    session: Session, source_processing_run_id: UUID
) -> tuple[CleanedDocumentV1, str]:
    rows = session.execute(
        select(ProcessingDerivation, ContentDerivation)
        .join(
            ContentDerivation,
            ContentDerivation.id == ProcessingDerivation.derivation_id,
        )
        .where(ProcessingDerivation.processing_run_id == source_processing_run_id)
    ).all()
    by_kind = {mapping.kind: derivation for mapping, derivation in rows}
    extracted = by_kind.get("extracted")
    cleaned = by_kind.get("cleaned")
    if extracted is None or cleaned is None:
        raise ValueError("The reusable processing run has no complete derivations.")
    blocks = session.scalars(
        select(ContentBlock)
        .where(ContentBlock.derivation_id == cleaned.id)
        .order_by(ContentBlock.ordinal)
    ).all()
    document = CleanedDocumentV1(
        media_type=cleaned.media_type,
        title=cleaned.title,
        language=cleaned.language,
        blocks=[
            CanonicalBlock(
                id=block.block_id,
                ordinal=block.ordinal,
                type=block.block_type,
                text=block.text,
                page_number=block.page_number,
                bounding_box=block.bounding_box,
                heading_path=block.heading_path,
                source_span=block.source_span,
                attributes=block.attributes,
            )
            for block in blocks
        ],
        extractor_version=extracted.engine_version,
        cleaner_version=cleaned.engine_version,
        configuration_hash=cleaned.configuration_hash,
        input_hash=cleaned.input_hash,
        output_hash=cleaned.output_hash,
        transforms=cleaned.transforms,
        measurements=cleaned.measurements,
        findings=cleaned.findings,
        sensitive_findings=cleaned.sensitive_findings,
        sensitive_data_applied=cleaned.sensitive_data_applied,
    )
    return document, extracted.engine_version


def link_reused_derivations(
    session: Session,
    *,
    processing_run_id: UUID,
    source_processing_run_id: UUID,
    document_id: UUID,
    project_id: UUID,
    spans: dict[int, list[ChunkBlockSpanV1]],
):
    target_run = session.scalar(
        select(ProcessingRun).where(
            ProcessingRun.id == processing_run_id,
            ProcessingRun.document_id == document_id,
        )
    )
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.project_id == project_id,
        )
    )
    if target_run is None or document is None:
        raise ValueError("Processing ownership is invalid for derivation reuse.")
    mappings = session.scalars(
        select(ProcessingDerivation).where(
            ProcessingDerivation.processing_run_id == source_processing_run_id,
            ProcessingDerivation.document_id == document_id,
            ProcessingDerivation.project_id == project_id,
        )
    ).all()
    by_kind = {mapping.kind: mapping for mapping in mappings}
    if set(by_kind) != {"extracted", "cleaned"}:
        raise ValueError("The reusable processing run has incomplete derivation links.")
    for kind in ("extracted", "cleaned"):
        session.add(
            ProcessingDerivation(
                processing_run_id=processing_run_id,
                kind=kind,
                derivation_id=by_kind[kind].derivation_id,
                document_id=document_id,
                project_id=project_id,
                reused=True,
            )
        )
    session.flush()
    _persist_spans(
        session,
        processing_run_id,
        by_kind["cleaned"].derivation_id,
        spans,
    )


def list_derivations(
    session: Session,
    project_id: UUID,
    processing_run_id: UUID,
    principal: Principal,
):
    _require_run(session, project_id, processing_run_id)
    rows = session.scalars(
        select(ContentDerivation)
        .join(
            ProcessingDerivation,
            ProcessingDerivation.derivation_id == ContentDerivation.id,
        )
        .where(ContentDerivation.project_id == project_id)
        .where(ProcessingDerivation.processing_run_id == processing_run_id)
        .order_by(ContentDerivation.kind)
    ).all()
    protected = any(row.sensitive_data_applied for row in rows)
    role = project_role(session, project_id, principal)
    if protected and role in {"owner", "admin"}:
        authorize_sensitive_read(
            session,
            project_id,
            principal,
            action="sensitive_findings_read",
            resource_kind="processing_run",
            resource_id=processing_run_id,
        )
    items = [ContentDerivationRead.model_validate(row) for row in rows]
    if protected and role not in {"owner", "admin"}:
        items = [item.model_copy(update={"sensitive_findings": []}) for item in items]
    return {"items": items, "total": len(items)}


def list_blocks(
    session: Session,
    project_id: UUID,
    derivation_id: UUID,
    limit: int,
    offset: int,
    principal: Principal,
):
    derivation = session.scalar(
        select(ContentDerivation).where(
            ContentDerivation.id == derivation_id,
            ContentDerivation.project_id == project_id,
        )
    )
    if derivation is None:
        raise HTTPException(404, "Content derivation not found.")
    query = select(ContentBlock).where(ContentBlock.derivation_id == derivation_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(ContentBlock.ordinal).limit(limit).offset(offset)
    ).all()
    if not derivation.protected_text:
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    authorize_sensitive_read(
        session,
        project_id,
        principal,
        action="raw_artifact_read",
        resource_kind="content_derivation",
        resource_id=derivation.id,
    )
    keyring, data_key = _protected_derivation_key(session, derivation)
    items = []
    for block in rows:
        items.append(
            {
                "derivation_id": block.derivation_id,
                "ordinal": block.ordinal,
                "block_id": block.block_id,
                "block_type": block.block_type,
                "text": _block_text(block, derivation, keyring, data_key),
                "page_number": block.page_number,
                "bounding_box": block.bounding_box,
                "heading_path": block.heading_path,
                "source_span": block.source_span,
                "attributes": block.attributes,
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def list_cleaning_diff(
    session: Session,
    project_id: UUID,
    processing_run_id: UUID,
    limit: int,
    offset: int,
    principal: Principal,
):
    """Reconstruct a bounded diff from immutable block rows and transform audits."""

    _require_run(session, project_id, processing_run_id)
    derivation_rows = session.scalars(
        select(ContentDerivation)
        .join(
            ProcessingDerivation,
            ProcessingDerivation.derivation_id == ContentDerivation.id,
        )
        .where(
            ContentDerivation.project_id == project_id,
            ProcessingDerivation.processing_run_id == processing_run_id,
        )
    ).all()
    by_kind = {row.kind: row for row in derivation_rows}
    extracted = by_kind.get("extracted")
    cleaned = by_kind.get("cleaned")
    if extracted is None or cleaned is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    keyring = data_key = None
    if extracted.protected_text:
        authorize_sensitive_read(
            session,
            project_id,
            principal,
            action="full_diff_read",
            resource_kind="processing_run",
            resource_id=processing_run_id,
        )
        keyring, data_key = _protected_derivation_key(session, extracted)
    total = session.scalar(
        select(func.count()).where(ContentBlock.derivation_id == extracted.id)
    )
    before = session.scalars(
        select(ContentBlock)
        .where(ContentBlock.derivation_id == extracted.id)
        .order_by(ContentBlock.ordinal)
        .limit(limit)
        .offset(offset)
    ).all()
    ids = [block.block_id for block in before]
    after = (
        session.scalars(
            select(ContentBlock).where(
                ContentBlock.derivation_id == cleaned.id,
                ContentBlock.block_id.in_(ids),
            )
        ).all()
        if ids
        else []
    )
    cleaned_by_id = {block.block_id: block for block in after}
    attribution: dict[str, list[tuple[str, str]]] = {}
    for audit in cleaned.transforms or []:
        transform = audit.get("transform")
        if not isinstance(transform, str):
            continue
        for change in audit.get("changes") or []:
            block_id = change.get("block_id")
            reason = change.get("reason")
            if isinstance(block_id, str) and isinstance(reason, str):
                attribution.setdefault(block_id, []).append((transform, reason))
    items = []
    for block in before:
        current = cleaned_by_id.get(block.block_id)
        changes = attribution.get(block.block_id, [])
        before_text = _block_text(block, extracted, keyring, data_key)
        action = (
            "removed"
            if current is None
            else "rewritten"
            if current.text != before_text
            else "unchanged"
        )
        items.append(
            {
                "block_id": block.block_id,
                "block_type": block.block_type,
                "page_number": block.page_number,
                "before_text": before_text,
                "after_text": current.text if current is not None else None,
                "action": action,
                "transforms": list(dict.fromkeys(value[0] for value in changes)),
                "reasons": list(dict.fromkeys(value[1] for value in changes)),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def list_chunk_spans(
    session: Session,
    project_id: UUID,
    processing_run_id: UUID,
    chunk_ordinal: int,
):
    _require_run(session, project_id, processing_run_id)
    rows = session.scalars(
        select(ChunkBlockSpan)
        .where(
            ChunkBlockSpan.run_id == processing_run_id,
            ChunkBlockSpan.chunk_ordinal == chunk_ordinal,
        )
        .order_by(ChunkBlockSpan.span_ordinal)
    ).all()
    return {"items": rows, "total": len(rows)}


def list_chunks(
    session: Session,
    project_id: UUID,
    processing_run_id: UUID,
    limit: int,
    offset: int,
):
    """Return faithful evidence, embedding input and exact ordered lineage."""

    _require_run(session, project_id, processing_run_id)
    total = session.scalar(
        select(func.count()).where(Chunk.run_id == processing_run_id)
    )
    chunks = session.scalars(
        select(Chunk)
        .where(Chunk.run_id == processing_run_id)
        .order_by(Chunk.ordinal)
        .limit(limit)
        .offset(offset)
    ).all()
    ordinals = [chunk.ordinal for chunk in chunks]
    span_rows = (
        session.scalars(
            select(ChunkBlockSpan)
            .where(
                ChunkBlockSpan.run_id == processing_run_id,
                ChunkBlockSpan.chunk_ordinal.in_(ordinals),
            )
            .order_by(
                ChunkBlockSpan.chunk_ordinal,
                ChunkBlockSpan.span_ordinal,
            )
        ).all()
        if ordinals
        else []
    )
    spans: dict[int, list[ChunkBlockSpan]] = {}
    for span in span_rows:
        spans.setdefault(span.chunk_ordinal, []).append(span)
    all_rows = session.execute(
        select(Chunk.token_count, Chunk.chunk_role, Chunk.findings).where(
            Chunk.run_id == processing_run_id
        )
    ).all()
    indexed_tokens = sorted(
        token_count
        for token_count, role, _ in all_rows
        if role != "parent" and token_count is not None
    )
    oversize = sum(
        1
        for _, _, findings in all_rows
        for finding in findings or []
        if str(finding.get("code", "")).startswith("oversize_")
    )
    items = []
    for chunk in chunks:
        provenance = chunk.provenance or {}
        items.append(
            {
                "run_id": chunk.run_id,
                "ordinal": chunk.ordinal,
                "page_number": chunk.page_number,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "evidence_text": chunk.text,
                "embedding_text": chunk.embedding_text or chunk.text,
                "embedding_prefix": provenance.get("embedding_prefix") or "",
                "token_count": chunk.token_count,
                "embedding_token_count": chunk.embedding_token_count,
                "chunk_role": chunk.chunk_role,
                "parent_ordinal": chunk.parent_ordinal,
                "section_path": provenance.get("section_path") or [],
                "findings": chunk.findings or [],
                "spans": spans.get(chunk.ordinal, []),
            }
        )
    return {
        "items": items,
        "summary": {
            "minimum": indexed_tokens[0] if indexed_tokens else None,
            "median": median(indexed_tokens) if indexed_tokens else None,
            "p95": (
                indexed_tokens[ceil(len(indexed_tokens) * 0.95) - 1]
                if indexed_tokens
                else None
            ),
            "maximum": indexed_tokens[-1] if indexed_tokens else None,
            "indexed_count": sum(1 for _, role, _ in all_rows if role != "parent"),
            "stored_count": len(all_rows),
            "parent_count": sum(1 for _, role, _ in all_rows if role == "parent"),
            "oversize_finding_count": oversize,
        },
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _require_run(session: Session, project_id: UUID, processing_run_id: UUID):
    if (
        session.scalar(
            select(ProcessingRun.id)
            .join(Document, Document.id == ProcessingRun.document_id)
            .where(
                ProcessingRun.id == processing_run_id,
                Document.project_id == project_id,
            )
        )
        is None
    ):
        raise HTTPException(404, "Processing run not found.")


def page_thumbnail(
    session: Session,
    project_id: UUID,
    processing_run_id: UUID,
    page_number: int,
    principal: Principal,
) -> bytes:
    row = session.execute(
        select(Document, ProcessingRun)
        .join(ProcessingRun, ProcessingRun.document_id == Document.id)
        .where(
            ProcessingRun.id == processing_run_id,
            Document.project_id == project_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Processing run not found.")
    document, _ = row
    authorize_sensitive_read(
        session,
        project_id,
        principal,
        action="thumbnail_read",
        resource_kind="processing_run",
        resource_id=processing_run_id,
    )
    if document.media_type != "application/pdf":
        raise HTTPException(404, "Page thumbnails are available only for PDFs.")
    try:
        with artifact_storage.materialize(document) as path:
            return render_pdf_thumbnail(path, page_number)
    except IngestionStageError as exc:
        raise HTTPException(422, exc.message) from None
