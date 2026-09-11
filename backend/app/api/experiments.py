from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import Response
from app.api.routes import Database
from app.api.documents import Limit, Offset
from app.core.config import settings
from app.schemas.experiment import DatasetRead, ExperimentCreate, ExperimentRead
from app.services import datasets, experiments
from app.services.documents import project
from app.evaluation import evaluator

router = APIRouter(prefix="/api/projects/{project_id}")


@router.get("/datasets/example.csv")
def example(project_id: UUID, session: Database):
    project(session, project_id)
    return Response(
        datasets.EXAMPLE,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="example-dataset.csv"'},
    )


async def read_csv(file):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "Choose a CSV file.")
    return await file.read(settings.dataset_max_bytes + 1)


@router.post("/datasets/preview")
async def preview(
    project_id: UUID, session: Database, file: Annotated[UploadFile, File()]
):
    project(session, project_id)
    return datasets.preview(await read_csv(file))


@router.post("/datasets", response_model=DatasetRead, status_code=201)
async def upload(
    project_id: UUID,
    session: Database,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()],
    content_hash: Annotated[str, Form()],
    dataset_id: Annotated[UUID | None, Form()] = None,
):
    return datasets.import_version(
        session, project_id, name, await read_csv(file), content_hash, dataset_id
    )


@router.get("/datasets")
def list_datasets(
    project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0
):
    page = datasets.listing(session, project_id, limit, offset)
    page["items"] = [
        DatasetRead.model_validate(d).model_dump(mode="json") for d in page["items"]
    ]
    return page


@router.get("/datasets/{version_id}", response_model=DatasetRead)
def dataset(project_id: UUID, version_id: UUID, session: Database):
    return datasets.get_version(session, project_id, version_id)


@router.get("/experiments/options")
def options(project_id: UUID, session: Database):
    project(session, project_id)
    error = None
    try:
        evaluator.configured(list(evaluator.METRICS))
    except Exception as exc:
        # Configuration errors are application-generated, never provider payloads.
        error = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Evaluator or embedding configuration unavailable."
        )
    return {
        "metrics": evaluator.METRICS,
        "model": settings.evaluator_model,
        "error": error,
        "max_rows": settings.dataset_max_rows,
        "max_bytes": settings.dataset_max_bytes,
    }


@router.post("/experiments", response_model=ExperimentRead, status_code=202)
def create(project_id: UUID, request: ExperimentCreate, session: Database):
    return experiments.submit(session, project_id, request)


@router.get("/experiments")
def listing(project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0):
    page = experiments.listing(session, project_id, limit, offset)
    page["items"] = [
        ExperimentRead.model_validate(e).model_dump(mode="json") for e in page["items"]
    ]
    return page


@router.get("/experiments/{experiment_id}")
def detail(project_id: UUID, experiment_id: UUID, session: Database):
    return experiments.detail(session, project_id, experiment_id)


@router.post("/experiments/{experiment_id}/cancel", response_model=ExperimentRead)
def cancel(project_id: UUID, experiment_id: UUID, session: Database):
    return experiments.cancel(session, project_id, experiment_id)


@router.get("/experiments/{experiment_id}/export.csv")
def export(project_id: UUID, experiment_id: UUID, session: Database):
    return Response(
        experiments.export_csv(session, project_id, experiment_id),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="experiment.csv"'},
    )
