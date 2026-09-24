"""Persistence and project-scoped reads for immutable content derivations."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.ingestion_content.contracts import (
    CleanedDocumentV1,
    ExtractedDocumentV1,
    ChunkBlockSpanV1,
)
from app.models.derivation import ChunkBlockSpan, ContentBlock, ContentDerivation
from app.models.document import Document, ProcessingRun


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
        measurements=document.measurements.model_dump(mode="json"),
        findings=[item.model_dump(mode="json") for item in document.findings],
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
):
    values = [
        dict(
            derivation_id=derivation_id,
            ordinal=block.ordinal,
            block_id=block.id,
            block_type=block.type,
            text=block.text,
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
        for block in document.blocks
    ]
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
    session.add_all([extracted_row, cleaned_row])
    session.flush()
    _persist_blocks(session, extracted_row.id, extracted)
    _persist_blocks(session, cleaned_row.id, cleaned)

    span_values = []
    for chunk_ordinal, chunk_spans in spans.items():
        for span_ordinal, span in enumerate(chunk_spans):
            span_values.append(
                dict(
                    run_id=processing_run_id,
                    chunk_ordinal=chunk_ordinal,
                    span_ordinal=span_ordinal,
                    derivation_id=cleaned_row.id,
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
    return extracted_row, cleaned_row


def list_derivations(session: Session, project_id: UUID, processing_run_id: UUID):
    _require_run(session, project_id, processing_run_id)
    rows = session.scalars(
        select(ContentDerivation)
        .where(
            ContentDerivation.project_id == project_id,
            ContentDerivation.processing_run_id == processing_run_id,
        )
        .order_by(ContentDerivation.kind)
    ).all()
    return {"items": rows, "total": len(rows)}


def list_blocks(
    session: Session,
    project_id: UUID,
    derivation_id: UUID,
    limit: int,
    offset: int,
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
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


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
