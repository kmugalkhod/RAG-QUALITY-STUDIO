"""Immutable canonical extraction, cleaning and chunk-lineage records."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ContentDerivation(Base):
    __tablename__ = "content_derivations"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_content_derivation_project"),
        UniqueConstraint(
            "id", "processing_run_id", name="uq_content_derivation_processing"
        ),
        UniqueConstraint(
            "id",
            "processing_run_id",
            "kind",
            name="uq_content_derivation_processing_kind",
        ),
        UniqueConstraint(
            "processing_run_id", "kind", name="uq_content_derivation_kind"
        ),
        ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            name="fk_content_derivation_document_project",
        ),
        ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["processing_runs.id", "processing_runs.document_id"],
            name="fk_content_derivation_processing_document",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "kind IN ('extracted','cleaned')", name="ck_content_derivation_kind"
        ),
        CheckConstraint("schema_version = 1", name="ck_content_derivation_schema"),
        CheckConstraint(
            "char_length(configuration_hash) = 64 "
            "AND char_length(input_hash) = 64 AND char_length(output_hash) = 64",
            name="ck_content_derivation_hashes",
        ),
        Index(
            "ix_content_derivations_project_run",
            "project_id",
            "processing_run_id",
            "kind",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    processing_run_id: Mapped[uuid.UUID]
    kind: Mapped[str] = mapped_column(String(16))
    schema_version: Mapped[int] = mapped_column(default=1)
    engine_version: Mapped[str] = mapped_column(String(120))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    output_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(1000))
    media_type: Mapped[str] = mapped_column(String(200))
    measurements: Mapped[dict] = mapped_column(JSONB)
    findings: Mapped[list] = mapped_column(JSONB)
    transforms: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ContentBlock(Base):
    __tablename__ = "content_blocks"
    __table_args__ = (
        UniqueConstraint(
            "derivation_id", "block_id", name="uq_content_block_stable_id"
        ),
        ForeignKeyConstraint(
            ["derivation_id"],
            ["content_derivations.id"],
            name="fk_content_block_derivation",
            ondelete="CASCADE",
        ),
        CheckConstraint("ordinal >= 0", name="ck_content_block_ordinal"),
        CheckConstraint(
            "block_type IN ('title','heading','paragraph','list_item','table','code',"
            "'quote','image_caption','footnote','unknown')",
            name="ck_content_block_type",
        ),
        CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="ck_content_block_page"
        ),
    )
    derivation_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[str] = mapped_column(String(64))
    block_type: Mapped[str] = mapped_column(String(24))
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None]
    bounding_box: Mapped[dict | None] = mapped_column(JSONB)
    heading_path: Mapped[list] = mapped_column(JSONB)
    source_span: Mapped[dict] = mapped_column(JSONB)
    attributes: Mapped[dict] = mapped_column(JSONB)


class ChunkBlockSpan(Base):
    __tablename__ = "chunk_block_spans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "chunk_ordinal"],
            ["chunks.run_id", "chunks.ordinal"],
            name="fk_chunk_block_span_chunk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["derivation_id", "run_id", "derivation_kind"],
            [
                "content_derivations.id",
                "content_derivations.processing_run_id",
                "content_derivations.kind",
            ],
            name="fk_chunk_block_span_derivation_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["derivation_id", "block_ordinal"],
            ["content_blocks.derivation_id", "content_blocks.ordinal"],
            name="fk_chunk_block_span_block",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "span_ordinal >= 0 AND block_ordinal >= 0",
            name="ck_chunk_block_span_ordinals",
        ),
        CheckConstraint(
            "block_start_char >= 0 AND block_end_char > block_start_char "
            "AND chunk_start_char >= 0 AND chunk_end_char > chunk_start_char",
            name="ck_chunk_block_span_offsets",
        ),
        CheckConstraint(
            "derivation_kind = 'cleaned'",
            name="ck_chunk_block_span_cleaned_derivation",
        ),
        Index("ix_chunk_block_spans_derivation", "derivation_id", "block_ordinal"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    chunk_ordinal: Mapped[int] = mapped_column(primary_key=True)
    span_ordinal: Mapped[int] = mapped_column(primary_key=True)
    derivation_id: Mapped[uuid.UUID]
    derivation_kind: Mapped[str] = mapped_column(String(16), default="cleaned")
    block_ordinal: Mapped[int]
    block_start_char: Mapped[int]
    block_end_char: Mapped[int]
    chunk_start_char: Mapped[int]
    chunk_end_char: Mapped[int]
