from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    index_id: UUID
    question: str = Field(min_length=1, max_length=8000)
    top_k: int = Field(default=5, strict=True, ge=1, le=50)


class QueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    index_id: UUID
    index_version: int
    question: str
    answer: str | None
    status: Literal["running", "succeeded", "insufficient_evidence", "failed"]
    error: str | None
    snapshot: dict
    created_at: datetime


class QueryPage(BaseModel):
    items: list[QueryRead]
    total: int
    limit: int
    offset: int
