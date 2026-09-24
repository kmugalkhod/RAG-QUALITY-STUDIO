"""Read contracts for canonical ingestion derivations and exact lineage."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ContentDerivationRead(ReadModel):
    id: UUID
    project_id: UUID
    document_id: UUID
    processing_run_id: UUID
    kind: Literal["extracted", "cleaned"]
    schema_version: Literal[1]
    engine_version: str
    configuration_hash: str
    input_hash: str
    output_hash: str
    title: str | None
    media_type: str
    measurements: dict[str, Any]
    findings: list[dict[str, Any]]
    transforms: list[dict[str, Any]]
    created_at: datetime


class ContentDerivationList(ReadModel):
    items: list[ContentDerivationRead]
    total: int


class ContentBlockRead(ReadModel):
    derivation_id: UUID
    ordinal: int
    block_id: str
    block_type: str
    text: str
    page_number: int | None
    bounding_box: dict[str, Any] | None
    heading_path: list[str]
    source_span: dict[str, Any]
    attributes: dict[str, Any]


class ContentBlockPage(ReadModel):
    items: list[ContentBlockRead]
    total: int
    limit: int
    offset: int


class ChunkBlockSpanRead(ReadModel):
    run_id: UUID
    chunk_ordinal: int
    span_ordinal: int
    derivation_id: UUID
    derivation_kind: Literal["cleaned"]
    block_ordinal: int
    block_start_char: int
    block_end_char: int
    chunk_start_char: int
    chunk_end_char: int


class ChunkBlockSpanList(ReadModel):
    items: list[ChunkBlockSpanRead]
    total: int


class ChunkInspectionRead(ReadModel):
    run_id: UUID
    ordinal: int
    page_number: int | None
    start_char: int
    end_char: int
    evidence_text: str
    embedding_text: str
    embedding_prefix: str
    token_count: int | None
    embedding_token_count: int | None
    chunk_role: Literal["leaf", "parent", "child"]
    parent_ordinal: int | None
    section_path: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    spans: list[ChunkBlockSpanRead] = Field(default_factory=list)


class ChunkDistributionRead(ReadModel):
    minimum: int | None
    median: float | None
    p95: int | None
    maximum: int | None
    indexed_count: int
    stored_count: int
    parent_count: int
    oversize_finding_count: int


class ChunkInspectionPage(ReadModel):
    items: list[ChunkInspectionRead]
    summary: ChunkDistributionRead
    total: int
    limit: int
    offset: int


class CleaningDiffRead(ReadModel):
    block_id: str
    block_type: str
    page_number: int | None
    before_text: str
    after_text: str | None
    action: Literal["unchanged", "rewritten", "removed"]
    transforms: list[str]
    reasons: list[str]


class CleaningDiffPage(ReadModel):
    items: list[CleaningDiffRead]
    total: int
    limit: int
    offset: int
