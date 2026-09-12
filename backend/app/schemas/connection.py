from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class S3Credentials(_Strict):
    kind: Literal["s3"]
    access_key_id: SecretStr = Field(min_length=1, max_length=256)
    secret_access_key: SecretStr = Field(min_length=1, max_length=4096)
    session_token: SecretStr | None = Field(default=None, min_length=1, max_length=8192)


class NotionCredentials(_Strict):
    kind: Literal["notion"]
    integration_token: SecretStr = Field(min_length=1, max_length=4096)


class ConfluenceCredentials(_Strict):
    kind: Literal["confluence"]
    site_url: HttpUrl
    email: SecretStr = Field(min_length=3, max_length=320)
    api_token: SecretStr = Field(min_length=1, max_length=4096)


Credentials = Annotated[
    S3Credentials | NotionCredentials | ConfluenceCredentials,
    Field(discriminator="kind"),
]


class SourceConnectionCreate(_Strict):
    name: str = Field(min_length=1, max_length=120)
    credentials: Credentials


class SourceConnectionRotate(_Strict):
    credentials: Credentials


class SourceConnectionRead(_Strict):
    id: UUID
    project_id: UUID
    name: str
    kind: Literal["s3", "notion", "confluence"]
    status: Literal["untested", "valid", "invalid", "unavailable"]
    redacted_summary: list[str]
    last_error: str | None
    last_tested_at: datetime | None
    rotated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourceConnectionPage(_Strict):
    items: list[SourceConnectionRead]
    total: int
    limit: int
    offset: int


class SourceConnectionSettings(_Strict):
    enabled: bool
    local_only: bool = True
    kinds: list[Literal["s3", "notion", "confluence"]] = Field(
        default_factory=lambda: ["s3", "notion", "confluence"]
    )
