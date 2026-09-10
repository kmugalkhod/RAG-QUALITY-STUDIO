from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.schemas.project import ProjectCreate, ProjectPage, ProjectRead
from app.services import projects

router = APIRouter(prefix="/api")
Database = Annotated[Session, Depends(get_session)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(session: Database) -> dict[str, str]:
    session.execute(
        text("SELECT id, name, description, created_at FROM projects LIMIT 0")
    )
    session.execute(text("SELECT storage_name, content_hash FROM documents LIMIT 0"))
    session.execute(text("SELECT status, execution_token FROM processing_runs LIMIT 0"))
    session.execute(text("SELECT run_id, ordinal FROM chunks LIMIT 0"))
    session.execute(
        text("SELECT embedding_config, embedded_count FROM index_versions LIMIT 0")
    )
    session.execute(text("SELECT vector_dims(embedding) FROM index_chunks LIMIT 0"))
    session.execute(
        text("SELECT pipeline_version_id, snapshot FROM query_runs LIMIT 0")
    )
    session.execute(text("SELECT project_id, name FROM pipelines LIMIT 0"))
    session.execute(text("SELECT execution, layout FROM pipeline_versions LIMIT 0"))
    return {"status": "ready"}


@router.get("/projects", response_model=ProjectPage)
def list_projects(
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return projects.list_projects(session, limit, offset)


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(data: ProjectCreate, session: Database):
    return projects.create_project(session, data)
