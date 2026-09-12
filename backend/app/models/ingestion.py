"""Durable ingestion coordination and per-source-item state."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pipeline_version_id", "project_id"],
            ["pipeline_versions.id", "pipeline_versions.project_id"],
            name="fk_ingestion_run_pipeline_project",
        ),
        ForeignKeyConstraint(
            ["knowledge_set_id", "project_id"],
            ["knowledge_sets.id", "knowledge_sets.project_id"],
            name="fk_ingestion_run_knowledge_set_project",
        ),
        UniqueConstraint("id", "project_id", name="uq_ingestion_run_project"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_ingestion_run_status",
        ),
        CheckConstraint(
            "stage IN ('processing','indexing','complete')",
            name="ck_ingestion_run_stage",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_ingestion_run_progress"),
        CheckConstraint(
            "discovered_count BETWEEN 1 AND 1000 "
            "AND processed_count BETWEEN 0 AND discovered_count "
            "AND failed_count BETWEEN 0 AND discovered_count "
            "AND processed_count + failed_count <= discovered_count "
            "AND chunk_count >= 0 AND embedded_count BETWEEN 0 AND chunk_count "
            "AND published_count BETWEEN 0 AND 1",
            name="ck_ingestion_run_counts",
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 10000 AND failures BETWEEN 0 AND 3",
            name="ck_ingestion_run_attempts",
        ),
        CheckConstraint(
            "status != 'succeeded' OR "
            "(stage = 'complete' AND progress = 100 AND published_count = 1 "
            "AND processed_count = discovered_count AND failed_count = 0 "
            "AND embedded_count = chunk_count)",
            name="ck_ingestion_run_complete",
        ),
        Index("ix_ingestion_runs_project_created", "project_id", "created_at", "id"),
        Index(
            "ix_ingestion_runs_status_dispatched",
            "status",
            "dispatched_at",
            "updated_at",
        ),
        Index(
            "uq_ingestion_active_knowledge_set",
            "knowledge_set_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    pipeline_version_id: Mapped[uuid.UUID]
    knowledge_set_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(16), default="queued")
    stage: Mapped[str] = mapped_column(String(24))
    progress: Mapped[int] = mapped_column(default=0)
    discovered_count: Mapped[int]
    processed_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    embedded_count: Mapped[int] = mapped_column(default=0)
    published_count: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    execution_token: Mapped[uuid.UUID | None]
    snapshot: Mapped[dict] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionRunItem(Base):
    __tablename__ = "ingestion_run_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["ingestion_runs.id", "ingestion_runs.project_id"],
            name="fk_ingestion_item_run_project",
        ),
        ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            name="fk_ingestion_item_document_project",
        ),
        ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["processing_runs.id", "processing_runs.document_id"],
            name="fk_ingestion_item_processing_document",
        ),
        CheckConstraint(
            "status IN ('processing','ready','succeeded','failed','cancelled')",
            name="ck_ingestion_item_status",
        ),
        CheckConstraint("chunk_count >= 0", name="ck_ingestion_item_chunks"),
        Index("ix_ingestion_items_run_status", "run_id", "status", "document_id"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    source_node_id: Mapped[str] = mapped_column(String(80))
    processing_run_id: Mapped[uuid.UUID]
    processing_created: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16))
    chunk_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
