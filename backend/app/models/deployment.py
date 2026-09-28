"""Organization-owned deployments and immutable answer release history."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AnswerDeployment(Base):
    __tablename__ = "answer_deployments"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "project_id",
            "pipeline_id",
            name="uq_answer_deployment_identity",
        ),
        UniqueConstraint(
            "id", "organization_id", "project_id", name="uq_answer_deployment_owner"
        ),
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
            name="fk_answer_deployment_project_org",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["pipeline_id", "project_id"],
            ["pipelines.id", "pipelines.project_id"],
            name="fk_answer_deployment_pipeline_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["active_release_id", "id"],
            [
                "answer_deployment_releases.id",
                "answer_deployment_releases.deployment_id",
            ],
            name="fk_answer_deployment_active_release",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_answer_deployment_name",
        ),
        CheckConstraint(
            "state IN ('paused','active','archived')", name="ck_answer_deployment_state"
        ),
        CheckConstraint(
            "state != 'active' OR active_release_id IS NOT NULL",
            name="ck_answer_deployment_active_pointer",
        ),
        CheckConstraint("revision >= 1", name="ck_answer_deployment_revision"),
        CheckConstraint(
            "rate_per_minute > 0 AND concurrent_runs > 0 AND queued_runs > 0 "
            "AND daily_budget_usd > 0 AND monthly_budget_usd > 0",
            name="ck_answer_deployment_limits",
        ),
        Index(
            "ix_answer_deployment_org_project",
            "organization_id",
            "project_id",
            "created_at",
            "id",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID]
    pipeline_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(16), default="paused")
    active_release_id: Mapped[uuid.UUID | None]
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_per_minute: Mapped[int] = mapped_column(Integer, default=30)
    concurrent_runs: Mapped[int] = mapped_column(Integer, default=2)
    queued_runs: Mapped[int] = mapped_column(Integer, default=20)
    daily_budget_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=5)
    monthly_budget_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=20)
    widget_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    widget_public_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    widget_origins: Mapped[list] = mapped_column(JSONB, default=list)
    widget_branding: Mapped[dict] = mapped_column(JSONB, default=dict)


class AnswerDeploymentRelease(Base):
    __tablename__ = "answer_deployment_releases"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id", "release_number", name="uq_answer_release_number"
        ),
        UniqueConstraint("id", "deployment_id", name="uq_answer_release_deployment"),
        ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id", "pipeline_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
                "answer_deployments.pipeline_id",
            ],
            name="fk_answer_release_deployment_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["pipeline_version_id", "pipeline_id", "project_id"],
            [
                "pipeline_versions.id",
                "pipeline_versions.pipeline_id",
                "pipeline_versions.project_id",
            ],
            name="fk_answer_release_pipeline_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["index_id", "project_id"],
            ["index_versions.id", "index_versions.project_id"],
            name="fk_answer_release_index_project",
            ondelete="RESTRICT",
        ),
        CheckConstraint("release_number >= 1", name="ck_answer_release_number"),
        CheckConstraint("char_length(note) <= 500", name="ck_answer_release_note"),
        Index("ix_answer_release_history", "deployment_id", "release_number"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID]
    organization_id: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID]
    pipeline_id: Mapped[uuid.UUID]
    pipeline_version_id: Mapped[uuid.UUID]
    index_id: Mapped[uuid.UUID]
    release_number: Mapped[int] = mapped_column(Integer)
    execution: Mapped[dict] = mapped_column(JSONB)
    execution_sha256: Mapped[str] = mapped_column(String(64))
    embedding_config: Mapped[dict] = mapped_column(JSONB)
    embedding_sha256: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    runtime_contract_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID]
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnswerDeploymentEvent(Base):
    __tablename__ = "answer_deployment_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_answer_event_deployment_owner",
            ondelete="RESTRICT",
        ),
        Index("ix_answer_event_history", "deployment_id", "created_at", "id"),
        Index("ix_answer_event_org", "organization_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID]
    organization_id: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID]
    event_type: Mapped[str] = mapped_column(String(40))
    actor_kind: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None]
    old_release_id: Mapped[uuid.UUID | None]
    new_release_id: Mapped[uuid.UUID | None]
    request_id: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnswerDeploymentKey(Base):
    __tablename__ = "answer_deployment_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_answer_key_deployment_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("prefix", name="uq_answer_key_prefix"),
        UniqueConstraint("id", "deployment_id", name="uq_answer_key_deployment"),
        CheckConstraint(
            "kind IN ('server','public_widget')", name="ck_answer_key_kind"
        ),
        Index(
            "uq_public_widget_key",
            "deployment_id",
            unique=True,
            postgresql_where=text("kind = 'public_widget'"),
        ),
        Index("ix_answer_key_family", "deployment_id", "client_id"),
        Index("ix_answer_key_validity", "deployment_id", "revoked_at", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID]
    organization_id: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]
    prefix: Mapped[str] = mapped_column(String(40))
    secret_hash: Mapped[str] = mapped_column(String(64))
    pepper_version: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="server")
    created_by: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotation_of_key_id: Mapped[uuid.UUID | None]


class WidgetToken(Base):
    __tablename__ = "widget_tokens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_widget_token_deployment_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["key_id", "deployment_id"],
            ["answer_deployment_keys.id", "answer_deployment_keys.deployment_id"],
            name="fk_widget_token_key",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("token_hash", name="uq_widget_token_hash"),
        Index("ix_widget_token_expiry", "expires_at"),
        Index(
            "ix_widget_token_visitor", "deployment_id", "visitor_binding", "created_at"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID]
    organization_id: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID]
    key_id: Mapped[uuid.UUID]
    token_hash: Mapped[str] = mapped_column(String(64))
    visitor_binding: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[uuid.UUID]
    site_origin: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeployedAnswerRun(Base):
    __tablename__ = "deployed_answer_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_deployed_run_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["release_id", "deployment_id"],
            [
                "answer_deployment_releases.id",
                "answer_deployment_releases.deployment_id",
            ],
            name="fk_deployed_run_release",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["key_id", "deployment_id"],
            ["answer_deployment_keys.id", "answer_deployment_keys.deployment_id"],
            name="fk_deployed_run_key",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "deployment_id",
            "client_id",
            "idempotency_key",
            name="uq_deployed_run_idempotency",
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','insufficient_evidence','failed','cancel_requested','cancelled')",
            name="ck_deployed_run_status",
        ),
        CheckConstraint(
            "cost_reservation_usd >= 0", name="ck_deployed_run_reservation"
        ),
        CheckConstraint("attempts >= 0", name="ck_deployed_run_attempts"),
        CheckConstraint(
            "caller_kind IN ('server_key','widget')", name="ck_deployed_run_caller_kind"
        ),
        Index("ix_deployed_run_history", "deployment_id", "created_at", "id"),
        Index("ix_deployed_run_org_status", "organization_id", "status", "created_at"),
        Index("ix_deployed_run_queue", "status", "dispatched_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID]
    deployment_id: Mapped[uuid.UUID]
    release_id: Mapped[uuid.UUID]
    key_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]
    caller_kind: Mapped[str] = mapped_column(String(16), default="server_key")
    widget_visitor_binding: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    question: Mapped[str | None] = mapped_column(String(8000))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    stage: Mapped[str] = mapped_column(String(40), default="admitted")
    answer: Mapped[str | None]
    citations: Mapped[list | None] = mapped_column(JSONB)
    evidence: Mapped[list | None] = mapped_column(JSONB)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    timing_ms: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    cost_reservation_usd: Mapped[float] = mapped_column(Numeric(12, 6))
    provider_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    cost_basis_version: Mapped[str] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    execution_token: Mapped[uuid.UUID | None]
    provider_call_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    result_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeploymentUsageBucket(Base):
    __tablename__ = "deployment_usage_buckets"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period",
            "period_start",
            name="uq_deployment_usage_period",
        ),
        CheckConstraint("period IN ('day','month')", name="ck_deployment_usage_period"),
        CheckConstraint(
            "reserved_usd >= 0 AND settled_usd >= 0 AND accepted_count >= 0",
            name="ck_deployment_usage_amounts",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[str] = mapped_column(String(100))
    period: Mapped[str] = mapped_column(String(8))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    reserved_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    settled_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeploymentUsageEntry(Base):
    __tablename__ = "deployment_usage_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id"], ["deployed_answer_runs.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("run_id", "entry_type", name="uq_deployment_usage_entry"),
        CheckConstraint(
            "entry_type IN ('reservation','settlement','release')",
            name="ck_deployment_usage_entry_type",
        ),
        CheckConstraint("amount_usd >= 0", name="ck_deployment_usage_entry_amount"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID]
    organization_id: Mapped[str] = mapped_column(String(100))
    entry_type: Mapped[str] = mapped_column(String(16))
    amount_usd: Mapped[float] = mapped_column(Numeric(12, 6))
    basis: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeploymentCommandReceipt(Base):
    __tablename__ = "deployment_command_receipts"
    __table_args__ = (
        UniqueConstraint(
            "principal_id", "command_kind", "key_hash", name="uq_deployment_command_key"
        ),
        Index("ix_deployment_command_expiry", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    principal_id: Mapped[uuid.UUID]
    project_id: Mapped[uuid.UUID]
    deployment_id: Mapped[uuid.UUID | None]
    command_kind: Mapped[str] = mapped_column(String(40))
    key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID]
    response: Mapped[dict] = mapped_column(JSONB)
    secret_issued: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
