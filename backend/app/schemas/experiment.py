from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricName = Literal["faithfulness", "response_relevancy", "context_recall"]


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    dataset_version_id: UUID
    pipeline_version_ids: list[UUID] = Field(min_length=1, max_length=2)
    metrics: list[MetricName] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.pipeline_version_ids)) != len(self.pipeline_version_ids) or len(
            set(self.metrics)
        ) != len(self.metrics):
            raise ValueError("Select distinct pipeline versions and metrics.")
        return self


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset_id: UUID
    project_id: UUID
    name: str
    version: int
    content_hash: str
    rows: list[dict]
    created_at: datetime


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    dataset_version_id: UUID
    name: str
    status: str
    snapshot: dict
    progress: int
    total: int
    cancel_requested: bool
    error: str | None
    created_at: datetime


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    candidate: int
    ordinal: int
    query_run_id: UUID | None
    status: str
    stage: str
    output: dict
    metrics: dict
    error: str | None
