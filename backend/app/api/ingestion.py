from uuid import UUID

from fastapi import APIRouter

from app.api.documents import Limit, Offset
from app.api.routes import Database
from app.schemas.ingestion import (
    IngestionPreviewRead,
    IngestionPreviewRequest,
    IngestionRunItemPage,
    IngestionRunPage,
    IngestionRunRead,
)
from app.services import ingestion, pipelines


router = APIRouter(prefix="/api/projects/{project_id}")


@router.post("/ingestion-previews", response_model=IngestionPreviewRead)
def preview(project_id: UUID, request: IngestionPreviewRequest, session: Database):
    pipelines.validate_ingestion(session, project_id, request.execution)
    return ingestion.preview(session, project_id, request.execution)


@router.post(
    "/pipelines/{pipeline_id}/versions/{version_id}/ingestion-runs",
    response_model=IngestionRunRead,
    status_code=202,
)
def start_run(project_id: UUID, pipeline_id: UUID, version_id: UUID, session: Database):
    return ingestion.start_run(session, project_id, pipeline_id, version_id)


@router.get("/ingestion-runs", response_model=IngestionRunPage)
def list_runs(
    project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0
):
    return ingestion.list_runs(session, project_id, limit, offset)


@router.get("/ingestion-runs/{run_id}", response_model=IngestionRunRead)
def get_run(project_id: UUID, run_id: UUID, session: Database):
    return ingestion.read_run(session, ingestion.get_run(session, project_id, run_id))


@router.get("/ingestion-runs/{run_id}/items", response_model=IngestionRunItemPage)
def list_items(
    project_id: UUID,
    run_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return ingestion.list_items(session, project_id, run_id, limit, offset)


@router.post("/ingestion-runs/{run_id}/cancel", response_model=IngestionRunRead)
def cancel_run(project_id: UUID, run_id: UUID, session: Database):
    return ingestion.cancel_run(session, project_id, run_id)
