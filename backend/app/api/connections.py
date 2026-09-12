from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.routes import Database
from app.core.config import settings
from app.core.connection_secrets import ConnectionKeyring, SecretConfigurationError
from app.models.project import Project
from app.schemas.connection import (
    SourceConnectionCreate,
    SourceConnectionPage,
    SourceConnectionRead,
    SourceConnectionRotate,
    SourceConnectionSettings,
)
from app.services import connections


router = APIRouter(prefix="/api/projects/{project_id}/source-connections")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


def _local_request(request: Request) -> bool:
    host = request.url.hostname
    if host not in LOCAL_HOSTS:
        return False
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
        return False
    return not any(
        request.headers.get(name)
        for name in ("forwarded", "x-forwarded-host", "x-original-host")
    )


def connection_settings(request: Request) -> SourceConnectionSettings:
    local = _local_request(request)
    configured = False
    if local:
        try:
            ConnectionKeyring.from_settings(settings)
            configured = True
        except SecretConfigurationError:
            pass
    return SourceConnectionSettings(
        enabled=settings.source_connections_enabled and configured and local,
        local_only=True,
    )


def require_keyring(request: Request) -> ConnectionKeyring:
    if not _local_request(request):
        raise HTTPException(
            403, "Source connections are restricted to the local workspace."
        )
    if not settings.source_connections_enabled:
        raise HTTPException(503, "Source connection management is not enabled.")
    try:
        return ConnectionKeyring.from_settings(settings)
    except SecretConfigurationError as error:
        raise HTTPException(503, str(error)) from None


Keyring = Annotated[ConnectionKeyring, Depends(require_keyring)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/settings", response_model=SourceConnectionSettings)
def read_settings(project_id: UUID, request: Request, session: Database):
    if session.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found.")
    return connection_settings(request)


@router.get("", response_model=SourceConnectionPage)
def list_connections(
    project_id: UUID,
    session: Database,
    keyring: Keyring,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return connections.list_connections(session, project_id, limit, offset)


@router.post("", response_model=SourceConnectionRead, status_code=201)
def create_connection(
    project_id: UUID,
    data: SourceConnectionCreate,
    session: Database,
    keyring: Keyring,
):
    return connections.create(session, project_id, data, keyring)


@router.get("/{connection_id}", response_model=SourceConnectionRead)
def read_connection(
    project_id: UUID,
    connection_id: UUID,
    session: Database,
    keyring: Keyring,
):
    return connections.read(session, project_id, connection_id)


@router.post("/{connection_id}/test", response_model=SourceConnectionRead)
def test_connection(
    project_id: UUID,
    connection_id: UUID,
    session: Database,
    keyring: Keyring,
):
    return connections.test(session, project_id, connection_id, keyring)


@router.post("/{connection_id}/rotate", response_model=SourceConnectionRead)
def rotate_connection(
    project_id: UUID,
    connection_id: UUID,
    data: SourceConnectionRotate,
    session: Database,
    keyring: Keyring,
):
    return connections.rotate(session, project_id, connection_id, data, keyring)


@router.post("/{connection_id}/rewrap", response_model=SourceConnectionRead)
def rewrap_connection(
    project_id: UUID,
    connection_id: UUID,
    session: Database,
    keyring: Keyring,
):
    return connections.rewrap(session, project_id, connection_id, keyring)
