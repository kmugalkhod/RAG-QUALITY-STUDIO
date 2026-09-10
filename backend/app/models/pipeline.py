import uuid
from datetime import datetime
from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_pipeline_project"),
        Index("ix_pipeline_project_created", "project_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PipelineVersion(Base):
    __tablename__ = "pipeline_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pipeline_id", "project_id"], ["pipelines.id", "pipelines.project_id"]
        ),
        UniqueConstraint("pipeline_id", "version", name="uq_pipeline_version"),
        UniqueConstraint("id", "project_id", name="uq_pipeline_version_project"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID]
    project_id: Mapped[uuid.UUID]
    version: Mapped[int]
    name: Mapped[str]
    execution: Mapped[dict] = mapped_column(JSONB)
    layout: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
