"""Read contracts for canonical ingestion derivations and exact lineage."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
