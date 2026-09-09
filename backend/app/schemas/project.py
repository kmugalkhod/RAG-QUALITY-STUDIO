from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    created_at: datetime


class ProjectPage(BaseModel):
    items: list[ProjectRead]
    total: int
    limit: int
    offset: int
