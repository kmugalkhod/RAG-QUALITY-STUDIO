from uuid import UUID
from fastapi import APIRouter
from app.api.routes import Database
from app.api.documents import Limit, Offset
from app.schemas.query import QueryRequest, QueryRead, QueryPage
from app.services import queries

router = APIRouter(prefix="/api/projects/{project_id}/query-runs")


@router.post("", response_model=QueryRead, status_code=201)
def execute(project_id: UUID, request: QueryRequest, session: Database):
    return queries.execute(session, project_id, request)


@router.get("", response_model=QueryPage)
def list_runs(
    project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0
):
    return queries.list_runs(session, project_id, limit, offset)


@router.get("/{run_id}", response_model=QueryRead)
def get_run(project_id: UUID, run_id: UUID, session: Database):
    return queries.get_run(session, project_id, run_id)
