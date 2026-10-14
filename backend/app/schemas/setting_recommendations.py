"""Recommended source settings contracts (spec 0011)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ingestion import WebsiteConfig, WebsiteSelection


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingRecommendationRequest(Strict):
    target: Literal["website"]
    source_node_id: str = Field(
        min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    selection: WebsiteSelection
    # Maximum pages of the draft's other Website sources (pipeline budget).
    other_sources_max_pages: int = Field(default=0, strict=True, ge=0, le=2500)
    refresh: bool = False


class RecommendationField(Strict):
    path: str
    label: str
    value: Any
    basis: Literal["computed", "default", "user"]
    risk: Literal["low", "medium", "high"]
    rationale_code: str
    rationale: str
    check: bool


class RecommendationWarning(Strict):
    code: str
    message: str


class SettingRecommendationRead(Strict):
    id: UUID
    source_node_id: str
    target: Literal["website"]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "expired"]
    progress: int
    progress_step: (
        Literal["robots", "start_page", "sitemaps", "sample_pages", "validating"] | None
    )
    error: str | None
    inputs: dict[str, Any]
    probe_version: str
    rules_version: str
    recommended: WebsiteConfig | None
    fields: list[RecommendationField]
    warnings: list[RecommendationWarning]
    # Requests, robots facts and start-page measurements. No page text.
    evidence: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime


class SettingRecommendationCapability(Strict):
    enabled: bool
    page_ceiling: int


class ProvenanceField(Strict):
    basis: Literal["computed", "default", "user"]
    recommended: Any = None
    saved: Any = None
    rationale_code: str
    rationale: str


class ProvenanceNode(Strict):
    status: Literal["applied", "recommendation_unavailable"] = "applied"
    target: Literal["website"] | None = None
    recommendation_id: UUID | None = None
    entered_url: str | None = None
    analysed_at: datetime | None = None
    probe_version: str | None = None
    rules_version: str | None = None
    fields: dict[str, ProvenanceField] = Field(default_factory=dict)


class SettingsProvenanceV1(Strict):
    """Where each recommended setting of a saved version came from."""

    schema_version: Literal[1]
    nodes: dict[str, ProvenanceNode]
