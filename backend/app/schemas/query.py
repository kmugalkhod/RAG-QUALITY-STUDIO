from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


from app.schemas.retrieval import RetrievalInput


class QueryRequest(RetrievalInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    index_id: UUID
    question: str = Field(min_length=1, max_length=8000)


class QueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    index_id: UUID
    pipeline_version_id: UUID | None
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
