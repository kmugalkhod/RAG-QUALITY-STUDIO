"""Encrypted connector credentials and audit-safe lifecycle events."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SourceConnection(Base):
    __tablename__ = "source_connections"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_source_connection_project"),
        UniqueConstraint(
            "project_id", "name", name="uq_source_connection_project_name"
        ),
        CheckConstraint(
            "kind IN ('s3','notion','confluence')",
            name="ck_source_connection_kind",
        ),
        CheckConstraint(
            "status IN ('untested','valid','invalid','unavailable')",
            name="ck_source_connection_status",
        ),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_source_connection_name",
        ),
        CheckConstraint(
            "octet_length(secret_nonce) = 12",
            name="ck_source_connection_nonce",
        ),
        CheckConstraint(
            "octet_length(secret_ciphertext) >= 16",
            name="ck_source_connection_ciphertext",
        ),
        CheckConstraint(
            "secret_schema_version = 1",
            name="ck_source_connection_secret_schema",
        ),
        Index(
            "ix_source_connections_project_created",
            "project_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32))
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    secret_nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    key_version: Mapped[str] = mapped_column(String(32))
    secret_schema_version: Mapped[int] = mapped_column(Integer, default=1)
    redacted_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="untested")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceConnectionEvent(Base):
    __tablename__ = "source_connection_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["connection_id", "project_id"],
            ["source_connections.id", "source_connections.project_id"],
            name="fk_source_connection_event_connection_project",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "event_type IN ('created','credentials_rotated','rewrapped','tested')",
            name="ck_source_connection_event_type",
        ),
        CheckConstraint(
            "outcome IN ('succeeded','failed','unavailable')",
            name="ck_source_connection_event_outcome",
        ),
        Index(
            "ix_source_connection_events_connection_created",
            "connection_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID]
    connection_id: Mapped[uuid.UUID]
    event_type: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(32), default="local-admin")
    safe_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
