"""Durable, bounded source-preview jobs and inspectable outcomes."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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
            "status IN ('queued','running','succeeded','failed','cancelled','expired')",
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
            "pass_count >= 0 AND warn_count >= 0 AND exclude_count >= 0 "
            "AND quality_fail_count >= 0 AND pass_count + warn_count + "
            "exclude_count + quality_fail_count <= included_count",
            name="ck_source_preview_quality_counts",
        ),
        CheckConstraint(
            "known_compute_ms >= 0", name="ck_source_preview_known_compute"
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
    pass_count: Mapped[int] = mapped_column(default=0)
    warn_count: Mapped[int] = mapped_column(default=0)
    exclude_count: Mapped[int] = mapped_column(default=0)
    quality_fail_count: Mapped[int] = mapped_column(default=0)
    known_compute_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    execution_token: Mapped[uuid.UUID | None]
    execution: Mapped[dict] = mapped_column(JSONB)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    fetch_mode: Mapped[str] = mapped_column(String(24), default="network")
    cost_basis: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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
        CheckConstraint(
            "quality_decision IS NULL OR quality_decision IN ('pass','warn','exclude','fail')",
            name="ck_source_preview_item_quality",
        ),
        CheckConstraint(
            "processing_status IN ('pending','succeeded','failed','skipped')",
            name="ck_source_preview_item_processing_status",
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
    provider_revision: Mapped[str | None] = mapped_column(String(1000))
    media_type: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    depth: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(80))
    quality_decision: Mapped[str | None] = mapped_column(String(16))
    processing_status: Mapped[str] = mapped_column(String(16), default="pending")
    fetch_mode: Mapped[str] = mapped_column(String(24), default="network")
    processing_config_hash: Mapped[str | None] = mapped_column(String(64))
    findings: Mapped[list] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    stage_timings: Mapped[dict] = mapped_column(JSONB, default=dict)
    cost_basis: Mapped[dict] = mapped_column(JSONB, default=dict)
    duplicate_decision: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourcePreviewRepresentation(Base):
    __tablename__ = "source_preview_representations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["preview_id", "item_ordinal"],
            ["source_preview_items.preview_id", "source_preview_items.ordinal"],
            ondelete="CASCADE",
            name="fk_source_preview_representation_item",
        ),
        CheckConstraint(
            "stage IN ('raw','extracted','cleaned','diff','chunks')",
            name="ck_source_preview_representation_stage",
        ),
        CheckConstraint(
            "ordinal >= 0", name="ck_source_preview_representation_ordinal"
        ),
        Index(
            "ix_source_preview_representations_stage",
            "preview_id",
            "item_ordinal",
            "stage",
            "ordinal",
        ),
    )
    preview_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    item_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[str] = mapped_column(String(16), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_type: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
