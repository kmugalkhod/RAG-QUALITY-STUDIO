from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_kind: Literal["website"]
    source_config_hash: str
    source_identity: dict
    connector_version: str
    snapshot_number: int
    status: Literal["collecting", "ready", "failed", "cancelled"]
    discovered_count: int
    included_count: int
    excluded_count: int
    duplicate_count: int
    failed_count: int
    new_count: int
    changed_count: int
    unchanged_count: int
    removed_count: int
    total_bytes: int
    creating_ingestion_run_id: UUID
    downstream_index_count: int = 0
    error: str | None
    created_at: datetime
    collected_at: datetime | None


class SourceSnapshotPage(BaseModel):
    items: list[SourceSnapshotRead]
    total: int
    limit: int
    offset: int


class SourceSnapshotMemberRead(BaseModel):
    ordinal: int
    source_node_id: str
    source_item_id: UUID
    source_revision_id: UUID
    inclusion_state: Literal["included"]
    canonical_location: str
    media_type: str
    size_bytes: int
    fetched_at: datetime
    provider_revision: str | None
    provenance: dict = Field(default_factory=dict)


class SourceSnapshotMemberPage(BaseModel):
    items: list[SourceSnapshotMemberRead]
    total: int
    limit: int
    offset: int


class SourceSnapshotIndexRead(BaseModel):
    id: UUID
    knowledge_set_id: UUID
    knowledge_set_name: str
    version: int
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    chunk_count: int
    embedded_count: int
    is_current: bool
    ingestion_pipeline_id: UUID | None
    ingestion_pipeline_version_id: UUID | None
    ingestion_pipeline_name: str | None
    ingestion_pipeline_version: int | None
    created_at: datetime


class SourceSnapshotIndexPage(BaseModel):
    items: list[SourceSnapshotIndexRead]
    total: int
    limit: int
    offset: int
