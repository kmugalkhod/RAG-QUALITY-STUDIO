"""Encrypted organization model-provider keys and audit-safe lifecycle events."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ProviderCredentialRecord(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("scope_key", "provider", name="uq_provider_credential_scope"),
        CheckConstraint(
            "provider IN ('openrouter')", name="ck_provider_credential_kind"
        ),
        CheckConstraint(
            "status IN ('active','rejected')", name="ck_provider_credential_status"
        ),
        CheckConstraint(
            "scope_key = 'instance' OR scope_key = 'organization:' || organization_id",
            name="ck_provider_credential_scope",
        ),
        CheckConstraint(
            "octet_length(nonce) = 12", name="ck_provider_credential_nonce"
        ),
        CheckConstraint(
            "octet_length(ciphertext) >= 16", name="ck_provider_credential_ciphertext"
        ),
        CheckConstraint("schema_version = 1", name="ck_provider_credential_schema"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # "organization:<clerk org id>" or "instance" for local single-owner mode.
    scope_key: Mapped[str] = mapped_column(String(120))
    organization_id: Mapped[str | None] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(32))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    wrap_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    redacted_hint: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_by: Mapped[str] = mapped_column(String(500))
    updated_by: Mapped[str] = mapped_column(String(500))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProviderCredentialEvent(Base):
    """Kept after a key is deleted; never holds secret material."""

    __tablename__ = "provider_credential_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created','rotated','deleted','tested','rejected_by_provider')",
            name="ck_provider_credential_event_type",
        ),
        CheckConstraint(
            "outcome IN ('succeeded','failed')",
            name="ck_provider_credential_event_outcome",
        ),
        Index(
            "ix_provider_credential_events_scope_created",
            "scope_key",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope_key: Mapped[str] = mapped_column(String(120))
    credential_id: Mapped[uuid.UUID | None]
    provider: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
