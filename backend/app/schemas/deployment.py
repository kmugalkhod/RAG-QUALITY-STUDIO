"""Strict public contracts for saved answer deployments."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReleaseInput(Strict):
    pipeline_version_id: UUID
    index_id: UUID
    note: str = Field(default="", max_length=500)


class DeploymentCreate(ReleaseInput):
    name: str = Field(min_length=1, max_length=120)
    pipeline_id: UUID


class PromotionInput(Strict):
    release_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class ReasonInput(Strict):
    reason: str = Field(min_length=1, max_length=500)


class KeyCreate(Strict):
    label: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None


class QuestionInput(Strict):
    question: str = Field(min_length=1, max_length=8000)

    @model_validator(mode="after")
    def reject_blank(self):
        if not self.question.strip():
            raise ValueError("Question is required.")
        return self


class LimitsInput(Strict):
    rate_per_minute: int = Field(ge=1)
    concurrent_runs: int = Field(ge=1)
    queued_runs: int = Field(ge=1)
    daily_budget_usd: Decimal = Field(gt=0)
    monthly_budget_usd: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def hierarchy(self):
        if self.daily_budget_usd > self.monthly_budget_usd:
            raise ValueError("Daily budget must not exceed monthly budget.")
        return self


DeploymentState = Literal["paused", "active", "archived"]
RunState = Literal[
    "queued",
    "running",
    "succeeded",
    "insufficient_evidence",
    "failed",
    "cancel_requested",
    "cancelled",
]


class PublicError(Strict):
    code: str
    message: str
    request_id: str
    details: list[dict] = Field(default_factory=list)


class ErrorEnvelope(Strict):
    error: PublicError


class DeploymentRead(Strict):
    id: UUID
    organization_id: str
    project_id: UUID
    pipeline_id: UUID
    name: str
    state: DeploymentState
    active_release_id: UUID | None
    revision: int
    accepting_questions: bool
    created_at: datetime


class ReleaseRead(Strict):
    id: UUID
    release_number: int
    pipeline_version_id: UUID
    index_id: UUID
    execution_sha256: str
    embedding_sha256: str
    created_at: datetime
    note: str


class Page(Strict):
    items: list[dict]
    total: int
    limit: int
    offset: int


class WidgetBranding(Strict):
    title: str = Field(default="Ask a question", min_length=1, max_length=60)
    greeting: str = Field(default="How can I help?", max_length=240)
    color: Literal["blue", "slate", "green"] = "blue"
    position: Literal["left", "right"] = "right"


class WidgetSettingsInput(Strict):
    enabled: bool
    public_enabled: bool = False
    allowed_origins: list[str] = Field(max_length=20)
    branding: WidgetBranding


class WidgetExchangeInput(Strict):
    visitor_session_id: str = Field(
        min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    site_origin: str = Field(min_length=8, max_length=255)
