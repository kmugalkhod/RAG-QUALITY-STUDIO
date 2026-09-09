from uuid import UUID
from fastapi import APIRouter
from app.api.routes import Database
from app.api.documents import Limit, Offset
from app.providers import embeddings
from app.schemas.index import IndexRead, IndexPage, RetrievalRequest, RetrievalRead
from app.services import indexes
from app.services.documents import project

router = APIRouter(prefix="/api/projects/{project_id}")


@router.get("/embedding-settings")
def embedding_settings(project_id: UUID, session: Database):
    project(session, project_id)
    try:
        return {"configured": True, "config": embeddings.configured(), "error": None}
    except embeddings.EmbeddingError as exc:
        return {"configured": False, "config": None, "error": str(exc)}


@router.post("/indexes", response_model=IndexRead, status_code=202)
def create_index(project_id: UUID, session: Database):
    return indexes.create_index(session, project_id)


@router.get("/indexes", response_model=IndexPage)
def list_indexes(
    project_id: UUID, session: Database, limit: Limit = 20, offset: Offset = 0
):
    return indexes.list_indexes(session, project_id, limit, offset)


@router.get("/indexes/{index_id}", response_model=IndexRead)
def get_index(project_id: UUID, index_id: UUID, session: Database):
    return indexes.get_index(session, project_id, index_id)


@router.post("/indexes/{index_id}/cancel", response_model=IndexRead)
def cancel_index(project_id: UUID, index_id: UUID, session: Database):
    return indexes.cancel_index(session, project_id, index_id)


@router.post("/retrieval", response_model=RetrievalRead)
def retrieve(project_id: UUID, request: RetrievalRequest, session: Database):
    return indexes.retrieve(session, project_id, request)
