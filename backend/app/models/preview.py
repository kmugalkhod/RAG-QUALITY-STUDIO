"""Durable, bounded source-preview jobs and inspectable outcomes."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SourcePreview(Base):
    __tablename__ = "source_previews"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_source_preview_project"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_source_preview_status",
        ),
        CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_source_preview_progress"
        ),
        CheckConstraint(
            "discovered_count >= 0 AND included_count >= 0 "
            "AND excluded_count >= 0 AND duplicate_count >= 0 "
            "AND failed_count >= 0 AND included_count + excluded_count + "
            "duplicate_count + failed_count = discovered_count",
            name="ck_source_preview_counts",
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 10000 AND failures BETWEEN 0 AND 3",
            name="ck_source_preview_attempts",
        ),
        CheckConstraint(
            "status != 'succeeded' OR progress = 100",
            name="ck_source_preview_complete",
        ),
        Index("ix_source_previews_project_created", "project_id", "created_at", "id"),
        Index(
            "ix_source_previews_status_dispatched",
            "status",
            "dispatched_at",
            "updated_at",
        ),
        Index(
            "uq_source_preview_active_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(default=0)
    discovered_count: Mapped[int] = mapped_column(default=0)
    included_count: Mapped[int] = mapped_column(default=0)
    excluded_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    execution_token: Mapped[uuid.UUID | None]
    execution: Mapped[dict] = mapped_column(JSONB)
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


class SourcePreviewItem(Base):
    __tablename__ = "source_preview_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('included','excluded','duplicate','failed')",
            name="ck_source_preview_item_status",
        ),
        CheckConstraint("ordinal >= 0", name="ck_source_preview_item_ordinal"),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_source_preview_item_size",
        ),
        Index("ix_source_preview_items_status", "preview_id", "status", "ordinal"),
    )
    preview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_previews.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_node_id: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str | None] = mapped_column(String(4000))
    display_name: Mapped[str] = mapped_column(String(500))
    canonical_location: Mapped[str | None] = mapped_column(String(4000))
    media_type: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    depth: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
