from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.providers.embeddings import EmbeddingConfig
from app.schemas.retrieval import RetrievalInput, RetrievalSettings


class IndexRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    version: int
    embedding_config: EmbeddingConfig
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    chunk_count: int
    embedded_count: int
    attempts: int
    failures: int
    error: str | None
    created_at: datetime


class IndexPage(BaseModel):
    items: list[IndexRead]
    total: int
    limit: int
    offset: int


class RetrievalRequest(RetrievalInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    index_id: UUID
    query: str = Field(min_length=1, max_length=8000)


class Evidence(BaseModel):
    rank: int
    document_id: UUID
    filename: str
    content_hash: str
    run_id: UUID
    processing_version: int
    ordinal: int
    page_number: int | None
    start_char: int
    end_char: int
    text: str
    cosine_distance: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    vector_rank: int | None = None
    keyword_rank: int | None = None


class RetrievalRead(BaseModel):
    index_id: UUID
    index_version: int
    embedding_config: EmbeddingConfig
    items: list[Evidence]
    retrieval: RetrievalSettings
    diagnostics: dict
    score_semantics: str = "Cosine distance: lower is closer; this is not confidence."
