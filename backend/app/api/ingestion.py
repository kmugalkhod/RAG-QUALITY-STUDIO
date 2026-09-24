from uuid import UUID

from fastapi import APIRouter, Request, Response

from app.api.connections import require_keyring
from app.api.documents import Limit, Offset
from app.api.routes import Database
from app.schemas.ingestion import (
    IngestionExecution,
    IngestionPreviewRequest,
    IngestionRunItemPage,
    IngestionRunPage,
    IngestionRunRead,
    IngestionRunStart,
    SourcePreviewItemPage,
    SourcePreviewRead,
)
from app.schemas.derivation import (
    CleaningDiffPage,
    ChunkBlockSpanList,
    ContentBlockPage,
    ContentDerivationList,
)
from app.schemas.extraction import ExtractionCapabilities
from app.schemas.source_snapshot import (
    SourceSnapshotIndexPage,
    SourceSnapshotMemberPage,
    SourceSnapshotPage,
    SourceSnapshotRead,
)
from app.services import derivations, ingestion, previews, source_snapshots
from app.services import documents
from app.ingestion_content.extractors import extraction_capabilities
from app.services import pipelines as pipeline_service


router = APIRouter(prefix="/api/projects/{project_id}")


@router.get("/ingestion-capabilities", response_model=ExtractionCapabilities)
def capabilities(project_id: UUID, session: Database):
    documents.project(session, project_id)
    return extraction_capabilities()


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
    data: IngestionRunStart | None = None,
):
    version = pipeline_service.get_version(session, project_id, pipeline_id, version_id)
    _protect_credentialed_source(
        request, IngestionExecution.model_validate(version.execution)
    )
    start = data or IngestionRunStart()
    return ingestion.start_run(
        session,
        project_id,
        pipeline_id,
        version_id,
        source_input=start.source_input,
        destination=start.destination,
        reuse_stored=start.reuse_stored,
    )


@router.get("/ingestion-runs", response_model=IngestionRunPage)
def list_runs(
    project_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
    pipeline_version_id: UUID | None = None,
):
    return ingestion.list_runs(
        session,
        project_id,
        limit,
        offset,
        pipeline_version_id=pipeline_version_id,
    )


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


@router.get(
    "/processing-runs/{processing_run_id}/derivations",
    response_model=ContentDerivationList,
)
def list_content_derivations(
    project_id: UUID, processing_run_id: UUID, session: Database
):
    return derivations.list_derivations(session, project_id, processing_run_id)


@router.get(
    "/content-derivations/{derivation_id}/blocks",
    response_model=ContentBlockPage,
)
def list_content_blocks(
    project_id: UUID,
    derivation_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return derivations.list_blocks(session, project_id, derivation_id, limit, offset)


@router.get(
    "/processing-runs/{processing_run_id}/cleaning-diff",
    response_model=CleaningDiffPage,
)
def list_cleaning_diff(
    project_id: UUID,
    processing_run_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return derivations.list_cleaning_diff(
        session, project_id, processing_run_id, limit, offset
    )


@router.get(
    "/processing-runs/{processing_run_id}/chunks/{chunk_ordinal}/spans",
    response_model=ChunkBlockSpanList,
)
def list_content_chunk_spans(
    project_id: UUID,
    processing_run_id: UUID,
    chunk_ordinal: int,
    session: Database,
):
    return derivations.list_chunk_spans(
        session, project_id, processing_run_id, chunk_ordinal
    )


@router.get("/processing-runs/{processing_run_id}/pages/{page_number}/thumbnail")
def page_thumbnail(
    project_id: UUID,
    processing_run_id: UUID,
    page_number: int,
    session: Database,
):
    if page_number < 1 or page_number > 2_000:
        return Response(status_code=422)
    content = derivations.page_thumbnail(
        session, project_id, processing_run_id, page_number
    )
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/ingestion-runs/{run_id}/cancel", response_model=IngestionRunRead)
def cancel_run(project_id: UUID, run_id: UUID, session: Database):
    return ingestion.cancel_run(session, project_id, run_id)


@router.get("/source-snapshots", response_model=SourceSnapshotPage)
def list_source_snapshots(
    project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0
):
    return source_snapshots.list_snapshots(session, project_id, limit, offset)


@router.get("/source-snapshots/{snapshot_id}", response_model=SourceSnapshotRead)
def get_source_snapshot(project_id: UUID, snapshot_id: UUID, session: Database):
    return source_snapshots.read(session, project_id, snapshot_id)


@router.get(
    "/source-snapshots/{snapshot_id}/items",
    response_model=SourceSnapshotMemberPage,
)
def list_source_snapshot_items(
    project_id: UUID,
    snapshot_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return source_snapshots.list_items(session, project_id, snapshot_id, limit, offset)


@router.get(
    "/source-snapshots/{snapshot_id}/indexes",
    response_model=SourceSnapshotIndexPage,
)
def list_source_snapshot_indexes(
    project_id: UUID,
    snapshot_id: UUID,
    session: Database,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return source_snapshots.list_indexes(
        session, project_id, snapshot_id, limit, offset
    )
