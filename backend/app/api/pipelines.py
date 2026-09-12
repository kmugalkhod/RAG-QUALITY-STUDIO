from uuid import UUID
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Query
from app.api.routes import Database
from app.api.documents import Limit, Offset
from app.core.config import settings
from app.providers import generation
from app.schemas.pipeline import (
    PipelineSaveRequest,
    PipelinePage,
    VersionRead,
    VersionPage,
    RunRequest,
    PreviewRequest,
    DEFAULT_TEMPLATE,
)
from app.schemas.query import QueryRead
from app.services import pipelines

router = APIRouter(prefix="/api/projects/{project_id}/pipelines")


@router.get("/options")
def options(project_id: UUID, session: Database):
    from app.services.documents import project

    project(session, project_id)
    error = None
    try:
        generation.configured()
    except generation.GenerationError as exc:
        error = str(exc)
    return {
        "models": generation.allowed_models(),
        "max_tokens": settings.chat_max_tokens,
        "context_tokens": settings.chat_context_tokens,
        "template": DEFAULT_TEMPLATE,
        "error": error,
    }


@router.post("/preview-runs", response_model=QueryRead, status_code=202)
def preview(
    project_id: UUID,
    request: PreviewRequest,
    session: Database,
    background: BackgroundTasks,
):
    row = pipelines.preview(session, project_id, request)
    background.add_task(pipelines.finish_run, row.id)
    return row


@router.get("", response_model=PipelinePage)
def listing(
    project_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
    kind: Literal["answer", "ingestion"] | None = Query(default=None),
):
    return pipelines.list_pipelines(session, project_id, limit, offset, kind)


@router.post("", response_model=VersionRead, status_code=201)
def create(project_id: UUID, request: PipelineSaveRequest, session: Database):
    return pipelines.save(session, project_id, request)


@router.post("/{pipeline_id}/versions", response_model=VersionRead, status_code=201)
def save(
    project_id: UUID,
    pipeline_id: UUID,
    request: PipelineSaveRequest,
    session: Database,
):
    return pipelines.save(session, project_id, request, pipeline_id)


@router.get("/{pipeline_id}/versions", response_model=VersionPage)
def versions(
    project_id: UUID,
    pipeline_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return pipelines.list_versions(session, project_id, pipeline_id, limit, offset)


@router.get("/{pipeline_id}/versions/{version_id}", response_model=VersionRead)
def version(project_id: UUID, pipeline_id: UUID, version_id: UUID, session: Database):
    return pipelines.get_version(session, project_id, pipeline_id, version_id)


@router.post(
    "/{pipeline_id}/versions/{version_id}/runs",
    response_model=QueryRead,
    status_code=202,
)
def run(
    project_id: UUID,
    pipeline_id: UUID,
    version_id: UUID,
    request: RunRequest,
    session: Database,
    background: BackgroundTasks,
):
    row = pipelines.start(session, project_id, pipeline_id, version_id, request)
    background.add_task(pipelines.finish_run, row.id)
    return row
