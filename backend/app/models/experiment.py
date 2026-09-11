import uuid
from datetime import datetime
from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("id", "project_id", name="uq_dataset_project"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str]


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_id", "project_id"], ["datasets.id", "datasets.project_id"]
        ),
        UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),
        UniqueConstraint("id", "project_id", name="uq_dataset_version_project"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID]
    project_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str]
    version: Mapped[int]
    content_hash: Mapped[str]
    rows: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_version_id", "project_id"],
            ["dataset_versions.id", "dataset_versions.project_id"],
        ),
        UniqueConstraint("id", "project_id", name="uq_experiment_project"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_experiment_status",
        ),
        Index("ix_experiment_project_created", "project_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID]
    dataset_version_id: Mapped[uuid.UUID]
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    snapshot: Mapped[dict] = mapped_column(JSONB)
    progress: Mapped[int] = mapped_column(default=0)
    total: Mapped[int]
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    execution_token: Mapped[uuid.UUID | None]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExperimentItem(Base):
    __tablename__ = "experiment_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "project_id"],
            ["experiments.id", "experiments.project_id"],
        ),
        ForeignKeyConstraint(
            ["pipeline_version_id", "project_id"],
            ["pipeline_versions.id", "pipeline_versions.project_id"],
        ),
        ForeignKeyConstraint(
            ["query_run_id", "project_id"], ["query_runs.id", "query_runs.project_id"]
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','skipped')",
            name="ck_experiment_item_status",
        ),
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    candidate: Mapped[int] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID]
    pipeline_version_id: Mapped[uuid.UUID]
    query_run_id: Mapped[uuid.UUID | None]
    status: Mapped[str] = mapped_column(default="pending")
    stage: Mapped[str] = mapped_column(default="generation")
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None]
