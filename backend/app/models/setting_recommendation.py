"""Durable recommended-settings jobs (spec 0011).

A row is a bounded probe of one source's site and the settings code computed
from it. Rows are never updated after a terminal status, and saved pipeline
versions copy what they used, so retention may prune old rows.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SettingRecommendation(Base):
    __tablename__ = "setting_recommendations"
    __table_args__ = (
        CheckConstraint(
            "target IN ('website')", name="ck_setting_recommendation_target"
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_setting_recommendation_status",
        ),
        CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_setting_recommendation_progress"
        ),
        CheckConstraint(
            "status != 'succeeded' OR progress = 100",
            name="ck_setting_recommendation_complete",
        ),
        CheckConstraint(
            "progress_step IS NULL OR progress_step IN "
            "('robots','start_page','sitemaps','sample_pages','validating')",
            name="ck_setting_recommendation_step",
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 10000 AND failures BETWEEN 0 AND 2",
            name="ck_setting_recommendation_attempts",
        ),
        Index(
            "ix_setting_recommendations_project_created",
            "project_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_setting_recommendations_status_dispatched",
            "status",
            "dispatched_at",
            "updated_at",
        ),
        Index(
            "ix_setting_recommendations_project_hash",
            "project_id",
            "inputs_hash",
            "created_at",
        ),
        Index(
            "uq_setting_recommendation_active_node",
            "project_id",
            "source_node_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    target: Mapped[str] = mapped_column(String(16))
    source_node_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(default=0)
    progress_step: Mapped[str | None] = mapped_column(String(24))
    # {selection, entered_url, other_sources_max_pages, page_ceiling}
    inputs: Mapped[dict] = mapped_column(JSONB)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    probe_version: Mapped[str] = mapped_column(String(32))
    rules_version: Mapped[str] = mapped_column(String(32))
    # Bounded measurements only: URLs without query strings, counts, statuses
    # and timings. Never page text, titles or headings.
    signals: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    recommended: Mapped[dict | None] = mapped_column(JSONB)
    fields: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    warnings: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    execution_token: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
