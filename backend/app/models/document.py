import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.project import Project  # noqa: F401


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_document_project"),
        CheckConstraint("size_bytes > 0", name="ck_document_size"),
        Index("ix_documents_project_created", "project_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    filename: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(40), unique=True)
    media_type: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_run_version"),
        UniqueConstraint("id", "document_id", name="uq_processing_run_document"),
        CheckConstraint(
            "chunk_size > 0 AND overlap >= 0 AND overlap < chunk_size",
            name="ck_run_chunking",
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_run_status",
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="ck_run_attempts"),
        Index("ix_runs_status_updated", "status", "updated_at"),
        Index(
            "uq_run_active_document",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    version: Mapped[int]
    chunk_size: Mapped[int]
    overlap: Mapped[int]
    config_version: Mapped[str] = mapped_column(String(32), default="characters-v1")
    parser_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    execution_token: Mapped[uuid.UUID | None]
    progress: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
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


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            "start_char >= 0 AND end_char > start_char", name="ck_chunk_offsets"
        ),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_runs.id"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    page_number: Mapped[int | None]
    start_char: Mapped[int]
    end_char: Mapped[int]
    text: Mapped[str] = mapped_column(Text)


Index(
    "ix_chunks_lexical",
    func.to_tsvector(text("'simple'::regconfig"), Chunk.text),
    postgresql_using="gin",
)
