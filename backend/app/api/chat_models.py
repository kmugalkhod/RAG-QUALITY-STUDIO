from typing import Annotated

from fastapi import APIRouter, Query

from app.api.routes import Database
from app.core.auth import CurrentPrincipal
from app.schemas.chat_model import CatalogPage, ChatModelChoice, ChatModelsRead
from app.services import chat_models

router = APIRouter(prefix="/api/organizations/current/chat-models")


@router.get("", response_model=ChatModelsRead)
def read_chat_models(session: Database, principal: CurrentPrincipal):
    return chat_models.read(session, principal)


@router.get("/catalog", response_model=CatalogPage)
def search_catalog(
    session: Database,
    principal: CurrentPrincipal,
    q: Annotated[str, Query(max_length=100)] = "",
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    return chat_models.search(session, principal, q, offset, limit)


@router.post("", response_model=ChatModelsRead)
def approve_chat_model(
    data: ChatModelChoice, session: Database, principal: CurrentPrincipal
):
    return chat_models.approve(session, principal, data.model_id)


@router.put("/default", response_model=ChatModelsRead)
def set_default_chat_model(
    data: ChatModelChoice, session: Database, principal: CurrentPrincipal
):
    return chat_models.set_default(session, principal, data.model_id)


# Model IDs contain "/", so the ID travels in the body rather than the path.
@router.post("/remove", response_model=ChatModelsRead)
def remove_chat_model(
    data: ChatModelChoice, session: Database, principal: CurrentPrincipal
):
    return chat_models.remove(session, principal, data.model_id)
