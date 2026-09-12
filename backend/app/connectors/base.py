"""Connector-neutral discovery and fetch contracts."""

from datetime import datetime
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectionCheck(Contract):
    status: Literal["available", "unavailable"]
    message: str = Field(min_length=1, max_length=500)


class ConnectorIssue(Contract):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    retry_after_seconds: float | None = Field(
        default=None, ge=0, le=86400, allow_inf_nan=False
    )


class DiscoveredItem(Contract):
    external_id: str = Field(min_length=1, max_length=1000)
    display_name: str = Field(min_length=1, max_length=500)
    canonical_location: str | None = Field(default=None, max_length=4000)
    media_type: str = Field(min_length=1, max_length=200)
    provider_revision: str | None = Field(default=None, max_length=1000)
    modified_at: datetime | None = None
    parent_external_id: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DiscoveryFailure(Contract):
    external_id: str | None = Field(default=None, max_length=1000)
    canonical_location: str | None = Field(default=None, max_length=4000)
    error: ConnectorIssue


class DiscoveryPage(Contract):
    items: tuple[DiscoveredItem, ...]
    failures: tuple[DiscoveryFailure, ...] = ()
    next_cursor: str | None = Field(default=None, max_length=4000)


class ChangedFetch(Contract):
    status: Literal["changed"]
    item: DiscoveredItem
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content: bytes | None = None
    stored_object_ref: str | None = Field(default=None, max_length=2000)
    fetched_at: datetime

    @model_validator(mode="after")
    def exactly_one_content_location(self):
        if (self.content is None) == (self.stored_object_ref is None):
            raise ValueError(
                "Changed fetches require bytes or a stored-object reference."
            )
        return self


class UnchangedFetch(Contract):
    status: Literal["unchanged"]
    item: DiscoveredItem
    prior_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    checked_at: datetime


class FailedFetch(Contract):
    status: Literal["failed"]
    item: DiscoveredItem
    error: ConnectorIssue


FetchResult = Annotated[
    ChangedFetch | UnchangedFetch | FailedFetch, Field(discriminator="status")
]


class ConnectorFailure(Exception):
    """Carries only a sanitized, retry-classified issue across connector boundaries."""

    def __init__(self, issue: ConnectorIssue):
        super().__init__(issue.message)
        self.issue = issue


@runtime_checkable
class SourceConnector(Protocol):
    kind: str
    config_version: str

    def validate(self, config: object, connection: object | None) -> None: ...

    def test_connection(self, connection: object | None) -> ConnectionCheck: ...

    def discover(self, config: object, cursor: str | None = None) -> DiscoveryPage: ...

    def fetch(
        self, item: DiscoveredItem, prior_revision: object | None = None
    ) -> FetchResult: ...
