"""Stable source identities, immutable revisions and website run provenance."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_source_item_project"),
        UniqueConstraint(
            "project_id", "kind", "identity_hash", name="uq_source_item_identity"
        ),
        CheckConstraint("kind = 'website'", name="ck_source_item_kind"),
        CheckConstraint("char_length(identity_hash) = 64", name="ck_source_item_hash"),
        Index("ix_source_items_project_kind", "project_id", "kind", "updated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(4000))
    identity_hash: Mapped[str] = mapped_column(String(64))
    canonical_location: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceRevision(Base):
    __tablename__ = "source_revisions"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_source_revision_project"),
        UniqueConstraint(
            "source_item_id", "content_hash", name="uq_source_revision_content"
        ),
        UniqueConstraint("document_id", name="uq_source_revision_document"),
        UniqueConstraint("processing_run_id", name="uq_source_revision_processing"),
        ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            name="fk_source_revision_item_project",
        ),
        ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            name="fk_source_revision_document_project",
        ),
        ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["processing_runs.id", "processing_runs.document_id"],
            name="fk_source_revision_processing_document",
        ),
        CheckConstraint(
            "char_length(content_hash) = 64", name="ck_source_revision_hash"
        ),
        CheckConstraint(
            "char_length(extracted_hash) = 64", name="ck_source_revision_extracted_hash"
        ),
        CheckConstraint("size_bytes > 0", name="ck_source_revision_size"),
        Index("ix_source_revisions_item_fetched", "source_item_id", "fetched_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID]
    source_item_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    processing_run_id: Mapped[uuid.UUID]
    content_hash: Mapped[str] = mapped_column(String(64))
    extracted_hash: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    artifact_storage_name: Mapped[str] = mapped_column(String(40), unique=True)
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(200))
    provider_revision: Mapped[str | None] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    extraction_config: Mapped[dict] = mapped_column(JSONB)
    provenance: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WebsiteRunItem(Base):
    __tablename__ = "website_run_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["ingestion_runs.id", "ingestion_runs.project_id"],
            name="fk_website_run_item_run_project",
        ),
        ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            name="fk_website_run_item_source_project",
        ),
        ForeignKeyConstraint(
            ["source_revision_id", "project_id"],
            ["source_revisions.id", "source_revisions.project_id"],
            name="fk_website_run_item_revision_project",
        ),
        CheckConstraint(
            "outcome IN ('new','changed','unchanged','removed','excluded','duplicate','failed')",
            name="ck_website_run_item_outcome",
        ),
        CheckConstraint(
            "status IN ('ready','succeeded','failed','cancelled')",
            name="ck_website_run_item_status",
        ),
        CheckConstraint("chunk_count >= 0", name="ck_website_run_item_chunks"),
        Index("ix_website_run_items_status", "run_id", "status", "ordinal"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[uuid.UUID]
    source_node_id: Mapped[str] = mapped_column(String(80))
    source_item_id: Mapped[uuid.UUID | None]
    source_revision_id: Mapped[uuid.UUID | None]
    canonical_location: Mapped[str | None] = mapped_column(String(4000))
    display_name: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    chunk_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IndexSourceRevision(Base):
    __tablename__ = "index_source_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["index_id", "project_id"],
            ["index_versions.id", "index_versions.project_id"],
            name="fk_index_source_revision_index_project",
        ),
        ForeignKeyConstraint(
            ["source_revision_id", "project_id"],
            ["source_revisions.id", "source_revisions.project_id"],
            name="fk_index_source_revision_revision_project",
        ),
        ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            name="fk_index_source_revision_item_project",
        ),
        UniqueConstraint("index_id", "source_item_id", name="uq_index_source_item"),
        Index("ix_index_source_revisions_item", "source_item_id", "index_id"),
    )
    index_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    source_revision_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    source_item_id: Mapped[uuid.UUID]
    source_node_id: Mapped[str] = mapped_column(String(80))
    project_id: Mapped[uuid.UUID]
