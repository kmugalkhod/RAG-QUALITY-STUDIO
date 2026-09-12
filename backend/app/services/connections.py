"""Project-scoped encrypted source-connection lifecycle."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.connections import tester_for
from app.core.connection_secrets import (
    ConnectionKeyring,
    EncryptedSecret,
    SecretDecryptionError,
)
from app.core.config import settings
from app.models.connection import SourceConnection, SourceConnectionEvent
from app.models.project import Project
from app.schemas.connection import (
    Credentials,
    NotionCredentials,
    S3Credentials,
    SourceConnectionCreate,
    SourceConnectionPage,
    SourceConnectionRead,
    SourceConnectionRotate,
)


credential_adapter = TypeAdapter(Credentials)
SAFE_TEST_MESSAGES = {
    "ok": None,
    "adapter_unavailable": "Connection testing is unavailable until this connector is installed.",
    "authentication_failed": "The provider rejected these credentials.",
    "permission_denied": "The credentials do not grant the required read access.",
    "endpoint_unreachable": "The provider could not be reached within the connection-test limit.",
}


def now():
    return datetime.now(UTC)


def _plain(credentials: Credentials) -> dict:
    if isinstance(credentials, S3Credentials):
        return {
            "kind": "s3",
            "access_key_id": credentials.access_key_id.get_secret_value(),
            "secret_access_key": credentials.secret_access_key.get_secret_value(),
            "session_token": (
                credentials.session_token.get_secret_value()
                if credentials.session_token
                else None
            ),
        }
    if isinstance(credentials, NotionCredentials):
        return {
            "kind": "notion",
            "integration_token": credentials.integration_token.get_secret_value(),
        }
    return {
        "kind": "confluence",
        "site_url": str(credentials.site_url),
        "email": credentials.email.get_secret_value(),
        "api_token": credentials.api_token.get_secret_value(),
    }


def _masked(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) >= 4 else "••••"


def _redacted(credentials: Credentials) -> dict:
    if isinstance(credentials, S3Credentials):
        return {
            "summary": [
                f"Access key {_masked(credentials.access_key_id.get_secret_value())}",
                "Temporary session" if credentials.session_token else "Long-lived key",
            ]
        }
    if isinstance(credentials, NotionCredentials):
        return {
            "summary": [
                f"Integration token {_masked(credentials.integration_token.get_secret_value())}"
            ]
        }
    host = credentials.site_url.host or "configured site"
    email = credentials.email.get_secret_value()
    domain = email.rsplit("@", 1)[-1] if "@" in email else "configured account"
    return {"summary": [host, f"Account at {domain}"]}


def _event(
    session: Session,
    connection: SourceConnection,
    event_type: str,
    outcome: str,
    **metadata,
):
    session.add(
        SourceConnectionEvent(
            project_id=connection.project_id,
            connection_id=connection.id,
            event_type=event_type,
            outcome=outcome,
            actor="local-admin",
            safe_metadata={"kind": connection.kind, **metadata},
        )
    )


def _read(connection: SourceConnection) -> SourceConnectionRead:
    return SourceConnectionRead(
        id=connection.id,
        project_id=connection.project_id,
        name=connection.name,
        kind=connection.kind,
        status=connection.status,
        redacted_summary=list(connection.redacted_metadata.get("summary", [])),
        last_error=connection.last_error,
        last_tested_at=connection.last_tested_at,
        rotated_at=connection.rotated_at,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def get(
    session: Session, project_id: UUID, connection_id: UUID, *, lock: bool = False
) -> SourceConnection:
    query = select(SourceConnection).where(
        SourceConnection.id == connection_id,
        SourceConnection.project_id == project_id,
    )
    connection = session.scalar(query.with_for_update() if lock else query)
    if connection is None:
        raise HTTPException(404, "Source connection not found.")
    return connection


def create(
    session: Session,
    project_id: UUID,
    data: SourceConnectionCreate,
    keyring: ConnectionKeyring,
) -> SourceConnectionRead:
    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "Connection name cannot be blank.")
    if session.scalar(
        select(SourceConnection.id).where(
            SourceConnection.project_id == project_id,
            SourceConnection.name == name,
        )
    ):
        raise HTTPException(409, "A connection with this name already exists.")
    total = session.scalar(
        select(func.count())
        .select_from(SourceConnection)
        .where(SourceConnection.project_id == project_id)
    )
    if total >= settings.source_connection_limit_per_project:
        raise HTTPException(409, "This project has reached its connection limit.")
    connection_id = uuid4()
    plain = _plain(data.credentials)
    encrypted = keyring.encrypt(plain, project_id, connection_id, plain["kind"])
    connection = SourceConnection(
        id=connection_id,
        project_id=project_id,
        name=name,
        kind=plain["kind"],
        secret_ciphertext=encrypted.ciphertext,
        secret_nonce=encrypted.nonce,
        key_version=encrypted.key_version,
        secret_schema_version=encrypted.schema_version,
        redacted_metadata=_redacted(data.credentials),
        status="untested",
    )
    session.add(connection)
    session.flush()
    _event(session, connection, "created", "succeeded")
    session.commit()
    session.refresh(connection)
    return _read(connection)


def list_connections(
    session: Session, project_id: UUID, limit: int, offset: int
) -> SourceConnectionPage:
    if session.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found.")
    where = SourceConnection.project_id == project_id
    total = session.scalar(
        select(func.count()).select_from(SourceConnection).where(where)
    )
    items = session.scalars(
        select(SourceConnection)
        .where(where)
        .order_by(SourceConnection.created_at.desc(), SourceConnection.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return SourceConnectionPage(
        items=[_read(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def read(session: Session, project_id: UUID, connection_id: UUID):
    return _read(get(session, project_id, connection_id))


def _decrypt(connection: SourceConnection, keyring: ConnectionKeyring) -> dict:
    value = keyring.decrypt(
        EncryptedSecret(
            connection.secret_ciphertext,
            connection.secret_nonce,
            connection.key_version,
            connection.secret_schema_version,
        ),
        connection.project_id,
        connection.id,
        connection.kind,
    )
    try:
        credentials = credential_adapter.validate_python(value)
        if credentials.kind != connection.kind:
            raise ValueError
    except Exception:
        raise SecretDecryptionError(
            "Stored connection credentials are unavailable."
        ) from None
    return _plain(credentials)


def rotate(
    session: Session,
    project_id: UUID,
    connection_id: UUID,
    data: SourceConnectionRotate,
    keyring: ConnectionKeyring,
):
    connection = get(session, project_id, connection_id, lock=True)
    if data.credentials.kind != connection.kind:
        raise HTTPException(422, "Credential type must match the connection type.")
    plain = _plain(data.credentials)
    encrypted = keyring.encrypt(plain, project_id, connection.id, connection.kind)
    connection.secret_ciphertext = encrypted.ciphertext
    connection.secret_nonce = encrypted.nonce
    connection.key_version = encrypted.key_version
    connection.secret_schema_version = encrypted.schema_version
    connection.redacted_metadata = _redacted(data.credentials)
    connection.status = "untested"
    connection.last_error = None
    connection.last_tested_at = None
    connection.rotated_at = connection.updated_at = now()
    _event(session, connection, "credentials_rotated", "succeeded")
    session.commit()
    session.refresh(connection)
    return _read(connection)


def rewrap(
    session: Session,
    project_id: UUID,
    connection_id: UUID,
    keyring: ConnectionKeyring,
):
    connection = get(session, project_id, connection_id, lock=True)
    value = _decrypt(connection, keyring)
    encrypted = keyring.encrypt(value, project_id, connection.id, connection.kind)
    connection.secret_ciphertext = encrypted.ciphertext
    connection.secret_nonce = encrypted.nonce
    connection.key_version = encrypted.key_version
    connection.secret_schema_version = encrypted.schema_version
    connection.updated_at = now()
    _event(session, connection, "rewrapped", "succeeded")
    session.commit()
    session.refresh(connection)
    return _read(connection)


def test(
    session: Session,
    project_id: UUID,
    connection_id: UUID,
    keyring: ConnectionKeyring,
):
    connection = get(session, project_id, connection_id, lock=True)
    credentials = _decrypt(connection, keyring)
    try:
        result = tester_for(connection.kind).check(credentials)
        if result.outcome not in ("succeeded", "failed", "unavailable"):
            raise ValueError
        message = SAFE_TEST_MESSAGES.get(result.code)
        if result.code not in SAFE_TEST_MESSAGES:
            raise ValueError
        status = {
            "succeeded": "valid",
            "failed": "invalid",
            "unavailable": "unavailable",
        }[result.outcome]
        outcome = result.outcome
    except Exception:
        status = "invalid"
        outcome = "failed"
        message = (
            "The connection check failed safely. Verify the credentials and try again."
        )
    connection.status = status
    connection.last_error = message
    connection.last_tested_at = connection.updated_at = now()
    safe_code = (
        result.code
        if "result" in locals() and result.code in SAFE_TEST_MESSAGES
        else "safe_failure"
    )
    _event(session, connection, "tested", outcome, code=safe_code)
    session.commit()
    session.refresh(connection)
    return _read(connection)
