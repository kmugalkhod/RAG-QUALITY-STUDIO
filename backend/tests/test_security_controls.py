"""Project-role, sensitive-access audit and encrypted-retention controls."""

import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import jwt
from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.auth import (
    Principal,
    _oidc_claims,
    authorize_sensitive_read,
    require_project_access,
)
from app.core.config import settings
from app.models.document import Document
from app.models.project import Project
from app.models.security import ProjectMembership, SensitiveAccessEvent, UserIdentity
from app.services import artifact_storage, documents


def _request(method: str):
    return SimpleNamespace(method=method)


def test_oidc_validates_signature_issuer_audience_and_expiry(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    current = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(settings, "auth_oidc_issuer", "https://issuer.example")
    monkeypatch.setattr(settings, "auth_oidc_audience", "rag-studio")
    monkeypatch.setattr(
        settings, "auth_oidc_jwks_url", "https://issuer.example/.well-known/jwks.json"
    )
    monkeypatch.setattr(settings, "auth_oidc_algorithms", ["RS256"])
    monkeypatch.setattr(
        "app.core.auth._jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
        ),
    )

    def request(token):
        return SimpleNamespace(headers={"authorization": f"Bearer {token}"})

    claims = {
        "sub": "synthetic-user",
        "iss": "https://issuer.example",
        "aud": "rag-studio",
        "iat": current,
        "exp": current + 60,
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    assert _oidc_claims(request(token))["sub"] == "synthetic-user"

    wrong_audience = jwt.encode(
        {**claims, "aud": "other"}, private_key, algorithm="RS256"
    )
    with pytest.raises(HTTPException) as rejected:
        _oidc_claims(request(wrong_audience))
    assert rejected.value.status_code == 401


def test_project_roles_deny_cross_project_and_viewer_writes(database):
    engine, _ = database
    user_id, project_id, unrelated_id = uuid4(), uuid4(), uuid4()
    principal = Principal(user_id, "synthetic-viewer", None, "oidc")
    with Session(engine) as session:
        session.add(UserIdentity(id=user_id, external_subject=principal.subject))
        session.add_all(
            [
                Project(id=project_id, name="Role test"),
                Project(id=unrelated_id, name="Other"),
            ]
        )
        session.flush()
        session.add(
            ProjectMembership(project_id=project_id, user_id=user_id, role="viewer")
        )
        session.commit()
    try:
        with Session(engine) as session:
            assert (
                require_project_access(project_id, _request("GET"), session, principal)
                == "viewer"
            )
            with pytest.raises(HTTPException) as write_error:
                require_project_access(project_id, _request("POST"), session, principal)
            assert write_error.value.status_code == 403
            with pytest.raises(HTTPException) as isolation_error:
                require_project_access(
                    unrelated_id, _request("GET"), session, principal
                )
            assert isolation_error.value.status_code == 404
    finally:
        with Session(engine) as session:
            session.execute(
                delete(Project).where(Project.id.in_([project_id, unrelated_id]))
            )
            session.execute(delete(UserIdentity).where(UserIdentity.id == user_id))
            session.commit()


def test_sensitive_read_is_owner_admin_only_and_audited(database):
    engine, _ = database
    project_id = uuid4()
    users = {
        role: Principal(uuid4(), f"synthetic-{role}", None, "oidc")
        for role in ("owner", "admin", "editor", "viewer")
    }
    with Session(engine) as session:
        session.add(Project(id=project_id, name="Sensitive audit"))
        session.add_all(
            UserIdentity(id=value.user_id, external_subject=value.subject)
            for value in users.values()
        )
        session.flush()
        session.add_all(
            ProjectMembership(project_id=project_id, user_id=value.user_id, role=role)
            for role, value in users.items()
        )
        session.commit()
    try:
        for role, principal in users.items():
            with Session(engine) as session:
                if role in {"owner", "admin"}:
                    authorize_sensitive_read(
                        session,
                        project_id,
                        principal,
                        action="raw_artifact_read",
                        resource_kind="document",
                        resource_id=None,
                    )
                else:
                    with pytest.raises(HTTPException) as error:
                        authorize_sensitive_read(
                            session,
                            project_id,
                            principal,
                            action="raw_artifact_read",
                            resource_kind="document",
                            resource_id=None,
                        )
                    assert error.value.status_code == 403
        with Session(engine) as session:
            outcomes = session.scalars(
                select(SensitiveAccessEvent.outcome)
                .where(SensitiveAccessEvent.project_id == project_id)
                .order_by(SensitiveAccessEvent.created_at, SensitiveAccessEvent.id)
            ).all()
            assert sorted(outcomes) == ["denied", "denied", "granted", "granted"]
    finally:
        with Session(engine) as session:
            session.execute(delete(Project).where(Project.id == project_id))
            session.execute(
                delete(UserIdentity).where(
                    UserIdentity.id.in_([value.user_id for value in users.values()])
                )
            )
            session.commit()


def test_artifact_lookup_includes_connector_documents(database):
    engine, _ = database
    project_id, document_id = uuid4(), uuid4()
    with Session(engine) as session:
        session.add(Project(id=project_id, name="Connector artifact"))
        session.flush()
        session.add(
            Document(
                id=document_id,
                project_id=project_id,
                filename="connector.txt",
                storage_name="c" * 40,
                media_type="text/plain",
                content_hash="0" * 64,
                size_bytes=1,
                origin_kind="website",
            )
        )
        session.commit()
    try:
        with Session(engine) as session:
            assert (
                documents.artifact_document(
                    session, project_id, document_id
                ).origin_kind
                == "website"
            )
            with pytest.raises(HTTPException) as upload_only:
                documents.document(session, project_id, document_id)
            assert upload_only.value.status_code == 404
    finally:
        with Session(engine) as session:
            session.execute(delete(Document).where(Document.id == document_id))
            session.execute(delete(Project).where(Project.id == project_id))
            session.commit()


def test_expired_encrypted_raw_is_deleted_without_deleting_history(
    database, tmp_path, monkeypatch
):
    engine, _ = database
    project_id, document_id = uuid4(), uuid4()
    monkeypatch.setattr(settings, "storage_path", tmp_path)
    monkeypatch.setattr(settings, "artifact_encryption_enabled", True)
    monkeypatch.setattr(settings, "artifact_encryption_mode", "local-keyring")
    monkeypatch.setattr(settings, "artifact_active_key", "test-v1")
    monkeypatch.setattr(
        settings,
        "artifact_keys",
        {"test-v1": SecretStr(base64.b64encode(bytes(range(32))).decode())},
    )
    stored = artifact_storage.store(
        b"synthetic retained source", project_id, document_id
    )
    with Session(engine) as session:
        session.add(Project(id=project_id, name="Retention test"))
        session.flush()
        session.add(
            Document(
                id=document_id,
                project_id=project_id,
                filename="retained.txt",
                media_type="text/plain",
                content_hash="0" * 64,
                size_bytes=25,
                **artifact_storage.model_values(stored),
            )
        )
        # Explicit expired value overrides the normal store retention window.
        session.flush()
        session.get(Document, document_id).raw_retained_until = datetime.now(
            timezone.utc
        ) - timedelta(seconds=1)
        session.commit()
    try:
        replacement = base64.b64encode(bytes(reversed(range(32)))).decode()
        monkeypatch.setattr(settings, "artifact_active_key", "test-v2")
        monkeypatch.setattr(
            settings,
            "artifact_keys",
            {
                "test-v1": SecretStr(base64.b64encode(bytes(range(32))).decode()),
                "test-v2": SecretStr(replacement),
            },
        )
        with Session(engine) as session:
            row = session.get(Document, document_id)
            result = artifact_storage.rewrap(session, row)
            assert result == {"status": "rewrapped", "key_version": "test-v2"}
        monkeypatch.setattr(
            settings, "artifact_keys", {"test-v2": SecretStr(replacement)}
        )
        with Session(engine) as session:
            with artifact_storage.materialize(
                session.get(Document, document_id)
            ) as path:
                assert path.read_bytes() == b"synthetic retained source"

        assert artifact_storage.cleanup_expired_raw_artifacts(engine) == 1
        assert not stored.path.exists()
        with Session(engine) as session:
            row = session.get(Document, document_id)
            assert row is not None
            assert row.artifact_state == "deleted"
            assert row.raw_deleted_at is not None
            assert row.artifact_wrapped_key is None
            assert session.get(Project, project_id) is not None
    finally:
        with Session(engine) as session:
            session.execute(delete(Document).where(Document.id == document_id))
            session.execute(delete(Project).where(Project.id == project_id))
            session.commit()
