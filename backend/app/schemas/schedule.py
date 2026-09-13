from datetime import datetime, time
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntervalCadence(Strict):
    kind: Literal["interval"]
    minutes: int = Field(strict=True, ge=15, le=10080)


class DailyCadence(Strict):
    kind: Literal["daily"]
    local_time: time
    timezone: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_timezone(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                "Schedule timezone must be a valid IANA timezone."
            ) from None
        if self.local_time.tzinfo is not None:
            raise ValueError("Daily local time cannot include a UTC offset.")
        return self


Cadence = Annotated[IntervalCadence | DailyCadence, Field(discriminator="kind")]


class ScheduleCreate(Strict):
    name: str = Field(min_length=1, max_length=120)
    pipeline_id: UUID
    pipeline_version_id: UUID
    cadence: Cadence
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip():
            raise ValueError("Schedule name cannot be blank.")
        return value


class ScheduleUpdate(Strict):
    name: str = Field(min_length=1, max_length=120)
    cadence: Cadence
    enabled: bool

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip():
            raise ValueError("Schedule name cannot be blank.")
        return value


class ScheduleRead(Strict):
    id: UUID
    project_id: UUID
    pipeline_id: UUID
    pipeline_version_id: UUID
    pipeline_version: int
    name: str
    status: Literal["paused", "enabled"]
    cadence: Cadence
    next_run_at: datetime | None
    last_run_id: UUID | None
    last_triggered_at: datetime | None
    last_outcome: (
        Literal["queued", "running", "succeeded", "failed", "cancelled", "skipped"]
        | None
    )
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class SchedulePage(Strict):
    items: list[ScheduleRead]
    total: int
    limit: int
    offset: int
