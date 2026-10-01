"""Chat models an organization admin approved from the OpenRouter catalog."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ChatModelApproval(Base):
    __tablename__ = "chat_model_approvals"
    __table_args__ = (
        UniqueConstraint(
            "scope_key", "provider", "model_id", name="uq_chat_model_approval"
        ),
        CheckConstraint("provider IN ('openrouter')", name="ck_chat_model_provider"),
        CheckConstraint(
            "scope_key = 'instance' OR scope_key = 'organization:' || organization_id",
            name="ck_chat_model_scope",
        ),
        CheckConstraint("context_length >= 2048", name="ck_chat_model_context"),
        # At most one default per scope.
        Index(
            "uq_chat_model_default",
            "scope_key",
            "provider",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Same scope keys as provider_credentials: "organization:<id>" or "instance".
    scope_key: Mapped[str] = mapped_column(String(120))
    organization_id: Mapped[str | None] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(32), default="openrouter")
    model_id: Mapped[str] = mapped_column(String(200))
    # Catalog snapshot at approval time; prices are estimates, NULL when unknown.
    label: Mapped[str] = mapped_column(String(200))
    context_length: Mapped[int] = mapped_column(Integer)
    prompt_usd_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    completion_usd_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    catalog_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
