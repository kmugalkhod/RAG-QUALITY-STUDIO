from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ProviderKeySave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=20, max_length=512)


class ProviderKeyRead(BaseModel):
    provider: Literal["openrouter"] = "openrouter"
    # "organization" for a Clerk organization, "instance" for local owner mode.
    scope: Literal["organization", "instance"]
    configured: bool
    status: Literal["active", "rejected"] | None = None
    redacted_hint: str | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None
    last_verified_at: datetime | None = None
    # Local mode only: the server environment key is used when nothing is stored.
    environment_fallback: bool = False
    can_manage: bool
    storage_available: bool
