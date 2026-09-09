from datetime import datetime
from typing import Literal, Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_size: int = Field(default=1000, gt=0, le=100000, strict=True)
    overlap: int = Field(default=200, ge=0, strict=True)

    @model_validator(mode="after")
    def validate_overlap(self) -> Self:
        if self.overlap >= self.chunk_size:
            raise ValueError("Overlap must be smaller than chunk size.")
        return self


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    version: int
    chunk_size: int
    overlap: int
    config_version: str
    parser_version: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempts: int
    progress: int
    chunk_count: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    filename: str
    media_type: str
    content_hash: str
    size_bytes: int
    created_at: datetime
    latest_run: RunRead | None = None


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ordinal: int
    page_number: int | None
    start_char: int
    end_char: int
    text: str


class DocumentPage(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


class RunPage(BaseModel):
    items: list[RunRead]
    total: int
    limit: int
    offset: int


class ChunkPage(BaseModel):
    items: list[ChunkRead]
    total: int
    limit: int
    offset: int
