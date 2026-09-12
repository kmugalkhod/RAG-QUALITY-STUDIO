"""Immutable index membership with resumable, fenced embedding progress."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
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


class KnowledgeSet(Base):
    __tablename__ = "knowledge_sets"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_knowledge_set_project"),
        UniqueConstraint("project_id", "name", name="uq_knowledge_set_name"),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_knowledge_set_name",
        ),
        ForeignKeyConstraint(
            ["current_ready_index_id", "project_id"],
            ["index_versions.id", "index_versions.project_id"],
            name="fk_knowledge_set_current_index_project",
            use_alter=True,
            ondelete="SET NULL (current_ready_index_id)",
        ),
        Index("ix_knowledge_sets_project_created", "project_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    current_ready_index_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IndexVersion(Base):
    __tablename__ = "index_versions"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_index_project"),
        UniqueConstraint(
            "knowledge_set_id", "version", name="uq_index_knowledge_set_version"
        ),
        UniqueConstraint("id", "dimensions", name="uq_index_dimensions"),
        CheckConstraint("dimensions BETWEEN 1 AND 16000", name="ck_index_dimensions"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_index_status",
        ),
        CheckConstraint(
            "chunk_count > 0 AND embedded_count BETWEEN 0 AND chunk_count",
            name="ck_index_counts",
        ),
        CheckConstraint(
            "status != 'succeeded' OR embedded_count = chunk_count",
            name="ck_index_complete",
        ),
        CheckConstraint(
            "failures BETWEEN 0 AND 3 AND attempts >= 0", name="ck_index_attempts"
        ),
        Index("ix_indexes_status_updated", "status", "updated_at"),
        Index(
            "uq_index_active_knowledge_set",
            "knowledge_set_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
        ForeignKeyConstraint(
            ["knowledge_set_id", "project_id"],
            ["knowledge_sets.id", "knowledge_sets.project_id"],
            name="fk_index_knowledge_set_project",
        ),
        ForeignKeyConstraint(
            ["ingestion_run_id", "project_id"],
            ["ingestion_runs.id", "ingestion_runs.project_id"],
            name="fk_index_ingestion_run_project",
            use_alter=True,
        ),
        UniqueConstraint("ingestion_run_id", name="uq_index_ingestion_run"),
        Index(
            "ix_indexes_knowledge_set_created", "knowledge_set_id", "created_at", "id"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    knowledge_set_id: Mapped[uuid.UUID]
    ingestion_run_id: Mapped[uuid.UUID | None]
    version: Mapped[int]
    dimensions: Mapped[int]
    embedding_config: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    chunk_count: Mapped[int]
    embedded_count: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    execution_token: Mapped[uuid.UUID | None]
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


class IndexChunk(Base):
    __tablename__ = "index_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "ordinal"], ["chunks.run_id", "chunks.ordinal"]
        ),
        ForeignKeyConstraint(
            ["index_id", "dimensions"],
            ["index_versions.id", "index_versions.dimensions"],
        ),
        CheckConstraint(
            "embedding IS NULL OR vector_dims(embedding) = dimensions",
            name="ck_embedding_dimensions",
        ),
        CheckConstraint(
            "embedding IS NULL OR vector_norm(embedding) > 0",
            name="ck_embedding_nonzero",
        ),
    )
    index_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    dimensions: Mapped[int]
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR())
