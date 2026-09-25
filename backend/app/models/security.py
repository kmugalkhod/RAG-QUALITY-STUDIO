"""Application identities, project roles and safe sensitive-access audit records."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("external_subject", name="uq_user_identity_subject"),
        Index("ix_user_identity_updated", "updated_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    external_subject: Mapped[str] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_membership_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["user_identities.id"],
            name="fk_project_membership_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "role IN ('owner','admin','editor','viewer')",
            name="ck_project_membership_role",
        ),
        Index("ix_project_membership_user", "user_id", "project_id"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SensitiveAccessEvent(Base):
    __tablename__ = "sensitive_access_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('raw_artifact_read','full_diff_read',"
            "'sensitive_findings_read','thumbnail_read','preview_protected_read',"
            "'artifact_key_rewrap')",
            name="ck_sensitive_access_action",
        ),
        CheckConstraint(
            "outcome IN ('granted','denied')",
            name="ck_sensitive_access_outcome",
        ),
        Index("ix_sensitive_access_project_time", "project_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_identities.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(String(40))
    resource_kind: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[uuid.UUID | None]
    outcome: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
