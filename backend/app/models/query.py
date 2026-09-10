import uuid
from datetime import datetime
from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    CheckConstraint,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class QueryRun(Base):
    __tablename__ = "query_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pipeline_version_id", "project_id"],
            ["pipeline_versions.id", "pipeline_versions.project_id"],
            name="fk_query_pipeline_version",
        ),
        ForeignKeyConstraint(
            ["index_id", "project_id"],
            ["index_versions.id", "index_versions.project_id"],
        ),
        CheckConstraint(
            "status IN ('running','succeeded','insufficient_evidence','failed')",
            name="ck_query_status",
        ),
        Index("ix_query_project_created", "project_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID]
    pipeline_version_id: Mapped[uuid.UUID | None]
    index_id: Mapped[uuid.UUID]
    index_version: Mapped[int]
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="running")
    error: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
