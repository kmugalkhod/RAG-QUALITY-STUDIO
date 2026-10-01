from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ModelId = Field(min_length=2, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]+$")


class ChatModelRead(BaseModel):
    id: str
    label: str
    # Usable prompt budget: the model's context capped by CHAT_CONTEXT_TOKENS.
    context_tokens: int
    # OpenRouter estimates in USD per million tokens; null when unknown.
    prompt_usd_per_mtok: float | None
    completion_usd_per_mtok: float | None
    catalog_fetched_at: datetime | None
    # "server": CHAT_MODEL / CHAT_MODELS. "organization": approved by an admin.
    source: Literal["server", "organization"]
    is_default: bool


class ChatModelsRead(BaseModel):
    scope: Literal["organization", "instance"]
    can_manage: bool
    context_ceiling: int
    default_model: str | None
    models: list[ChatModelRead]


class CatalogModelRead(BaseModel):
    id: str
    name: str
    context_length: int
    prompt_usd_per_mtok: float | None
    completion_usd_per_mtok: float | None
    approved: bool


class CatalogPage(BaseModel):
    items: list[CatalogModelRead]
    total: int
    offset: int
    limit: int
    fetched_at: datetime


class ChatModelChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = ModelId
