from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Request
from app.api.routes import Database
from app.schemas.document import (
    ChunkPage,
    DocumentPage,
    DocumentRead,
    ProcessingConfig,
    RunPage,
    RunRead,
)
from app.schemas.project import ProjectRead
from app.services import documents
from app.core.config import settings

router = APIRouter(prefix="/api/projects/{project_id}")
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("", response_model=ProjectRead)
def get_project(project_id: UUID, session: Database):
    return documents.project(session, project_id)


@router.get("/upload-settings")
def upload_settings(project_id: UUID, session: Database):
    documents.project(session, project_id)
    return {"max_upload_bytes": settings.max_upload_bytes}


async def validate_file_count(request: Request):
    form = await request.form()
    if len(form.multi_items()) != 1 or "file" not in form:
        raise HTTPException(
            422, "Upload exactly one file per request, using the file field."
        )


@router.post("/documents", response_model=DocumentRead, status_code=201)
def upload(
    project_id: UUID,
    session: Database,
    files: Annotated[list[UploadFile], File(alias="file")],
    _: Annotated[None, Depends(validate_file_count)],
):
    try:
        if len(files) != 1:
            raise HTTPException(422, "Upload exactly one file per request.")
        return documents.upload(session, project_id, files[0])
    finally:
        for file in files:
            file.file.close()


@router.get("/documents", response_model=DocumentPage)
def list_documents(
    project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0
):
    return documents.list_documents(session, project_id, limit, offset)


@router.post("/documents/{document_id}/runs", response_model=RunRead, status_code=202)
def start(
    project_id: UUID, document_id: UUID, config: ProcessingConfig, session: Database
):
    return documents.start(session, project_id, document_id, config)


@router.get("/documents/{document_id}/runs", response_model=RunPage)
def list_runs(
    project_id: UUID,
    document_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return documents.list_runs(session, project_id, document_id, limit, offset)


@router.get("/documents/{document_id}/runs/{run_id}", response_model=RunRead)
def get_run(project_id: UUID, document_id: UUID, run_id: UUID, session: Database):
    return documents.run(session, project_id, document_id, run_id)


@router.post("/documents/{document_id}/runs/{run_id}/cancel", response_model=RunRead)
def cancel(project_id: UUID, document_id: UUID, run_id: UUID, session: Database):
    return documents.cancel(session, project_id, document_id, run_id)


@router.get("/documents/{document_id}/runs/{run_id}/chunks", response_model=ChunkPage)
def chunks(
    project_id: UUID,
    document_id: UUID,
    run_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return documents.list_chunks(
        session, project_id, document_id, run_id, limit, offset
    )
