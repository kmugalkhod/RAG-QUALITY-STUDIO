import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120", name="ck_projects_name"
        ),
        CheckConstraint(
            "char_length(description) <= 2000", name="ck_projects_description"
        ),
        Index("ix_projects_created_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
