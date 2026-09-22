from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.providers.embeddings import EmbeddingConfig
from app.schemas.retrieval import RetrievalInput, RetrievalSettings


class KnowledgeSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    name: str
    current_ready_index_id: UUID | None
    created_at: datetime


class KnowledgeSetPage(BaseModel):
    items: list[KnowledgeSetRead]
    total: int
    limit: int
    offset: int


class IndexCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_set_id: UUID | None = None
    document_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=1000)


class IndexRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    knowledge_set_id: UUID
    knowledge_set_name: str
    version: int
    embedding_config: EmbeddingConfig
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    chunk_count: int
    embedded_count: int
    attempts: int
    failures: int
    processing_run_count: int
    is_current: bool
    source_snapshot_id: UUID | None = None
    source_snapshot_number: int | None = None
    source_snapshot_collected_at: datetime | None = None
    ingestion_pipeline_id: UUID | None = None
    ingestion_pipeline_name: str | None = None
    ingestion_pipeline_version: int | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    error: str | None
    created_at: datetime


class IndexPage(BaseModel):
    items: list[IndexRead]
    total: int
    limit: int
    offset: int


class IndexRecordRead(BaseModel):
    run_id: UUID
    ordinal: int
    document_id: UUID
    filename: str
    processing_version: int
    page_number: int | None
    start_char: int
    end_char: int
    text: str
    source_url: str | None = None
    section_path: list[str] = Field(default_factory=list)
    dimensions: int
    embedded: bool
    embedding_norm: float | None
    embedding_preview: list[float] = Field(default_factory=list)


class IndexRecordPage(BaseModel):
    items: list[IndexRecordRead]
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
    source_url: str | None = None
    section_path: list[str] = Field(default_factory=list)
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
