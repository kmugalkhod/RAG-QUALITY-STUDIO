from uuid import UUID

from fastapi import APIRouter, Request

from app.api.connections import require_keyring
from app.api.documents import Limit, Offset
from app.api.routes import Database
from app.schemas.ingestion import (
    IngestionExecution,
    IngestionPreviewRequest,
    IngestionRunItemPage,
    IngestionRunPage,
    IngestionRunRead,
    SourcePreviewItemPage,
    SourcePreviewRead,
)
from app.services import ingestion, previews
from app.services import pipelines as pipeline_service


router = APIRouter(prefix="/api/projects/{project_id}")


def _protect_credentialed_source(request: Request, execution: IngestionExecution):
    if any(
        node.type == "source" and node.config.kind in ("s3", "notion", "confluence")
        for node in execution.nodes
    ):
        require_keyring(request)


@router.post("/ingestion-previews", response_model=SourcePreviewRead, status_code=202)
def preview(
    project_id: UUID,
    data: IngestionPreviewRequest,
    request: Request,
    session: Database,
):
    _protect_credentialed_source(request, data.execution)
    return previews.start(session, project_id, data.execution)


@router.get("/source-previews/{preview_id}", response_model=SourcePreviewRead)
def get_preview(project_id: UUID, preview_id: UUID, session: Database):
    return previews.read(session, project_id, preview_id)


@router.get("/source-previews/{preview_id}/items", response_model=SourcePreviewItemPage)
def preview_items(
    project_id: UUID,
    preview_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return previews.items(session, project_id, preview_id, limit, offset)


@router.post("/source-previews/{preview_id}/cancel", response_model=SourcePreviewRead)
def cancel_preview(project_id: UUID, preview_id: UUID, session: Database):
    return previews.cancel(session, project_id, preview_id)


@router.post(
    "/pipelines/{pipeline_id}/versions/{version_id}/ingestion-runs",
    response_model=IngestionRunRead,
    status_code=202,
)
def start_run(
    project_id: UUID,
    pipeline_id: UUID,
    version_id: UUID,
    request: Request,
    session: Database,
):
    version = pipeline_service.get_version(session, project_id, pipeline_id, version_id)
    _protect_credentialed_source(
        request, IngestionExecution.model_validate(version.execution)
    )
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
