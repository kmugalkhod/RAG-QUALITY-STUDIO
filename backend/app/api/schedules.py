from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.documents import Limit, Offset
from app.api.ingestion import _protect_credentialed_source
from app.api.routes import Database
from app.models.pipeline import PipelineVersion
from app.schemas.ingestion import IngestionExecution, IngestionRunRead
from app.schemas.schedule import (
    ScheduleCreate,
    SchedulePage,
    ScheduleRead,
    ScheduleUpdate,
)
from app.services import schedules
from app.core.auth import require_project_access


router = APIRouter(
    prefix="/api/projects/{project_id}/ingestion-schedules",
    dependencies=[Depends(require_project_access)],
)


@router.get("", response_model=SchedulePage)
def listing(project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0):
    return schedules.list_schedules(session, project_id, limit, offset)


@router.post("", response_model=ScheduleRead, status_code=201)
def create(project_id: UUID, data: ScheduleCreate, request: Request, session: Database):
    version = schedules.version(
        session, project_id, data.pipeline_id, data.pipeline_version_id
    )
    _protect_credentialed_source(
        request, IngestionExecution.model_validate(version.execution)
    )
    return schedules.create(session, project_id, data)


@router.get("/{schedule_id}", response_model=ScheduleRead)
def read(project_id: UUID, schedule_id: UUID, session: Database):
    return schedules.serialize(session, schedules.get(session, project_id, schedule_id))


@router.post("/{schedule_id}", response_model=ScheduleRead)
def update(
    project_id: UUID,
    schedule_id: UUID,
    data: ScheduleUpdate,
    request: Request,
    session: Database,
):
    schedule = schedules.get(session, project_id, schedule_id)
    version = session.get(PipelineVersion, schedule.pipeline_version_id)
    _protect_credentialed_source(
        request, IngestionExecution.model_validate(version.execution)
    )
    return schedules.update(session, project_id, schedule_id, data)


@router.post("/{schedule_id}/run", response_model=IngestionRunRead, status_code=202)
def run(project_id: UUID, schedule_id: UUID, request: Request, session: Database):
    schedule = schedules.get(session, project_id, schedule_id)
    version = session.get(PipelineVersion, schedule.pipeline_version_id)
    _protect_credentialed_source(
        request, IngestionExecution.model_validate(version.execution)
    )
    return schedules.trigger(session, project_id, schedule_id)
