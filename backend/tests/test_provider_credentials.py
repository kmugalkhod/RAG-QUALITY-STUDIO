"""Organization OpenRouter keys: encryption, isolation, roles and adapter use."""

import base64
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.artifact_crypto import ArtifactUnavailableError
from app.core.auth import Principal, current_principal
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.project import Project
from app.models.provider_credential import (
    ProviderCredentialEvent,
    ProviderCredentialRecord,
)
from app.providers import credentials, generation
from app.providers import rate_limit
from app.services import provider_credentials

ORG_A_KEY = "sk-or-v1-" + "a" * 40 + "AAAA"
ORG_B_KEY = "sk-or-v1-" + "b" * 40 + "BBBB"


def admin(org="org_a"):
    return Principal(uuid4(), f"user_admin_{org}", None, "clerk", org, "org:admin")


def member(org="org_a"):
    return Principal(uuid4(), f"user_member_{org}", None, "clerk", org, "org:member")


@pytest.fixture
def encryption(monkeypatch):
    monkeypatch.setattr(settings, "artifact_encryption_enabled", True)
    monkeypatch.setattr(settings, "artifact_encryption_mode", "local-keyring")
    monkeypatch.setattr(
        settings,
        "artifact_keys",
        {"test-v1": SecretStr(base64.b64encode(bytes(range(32))).decode())},
    )
    monkeypatch.setattr(settings, "artifact_active_key", "test-v1")


@pytest.fixture
def keys(database, encryption, monkeypatch):
    """Clerk mode with two organizations and a verified-key double."""
    engine, _ = database
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("env-secret-key"))
    monkeypatch.setattr(
        provider_credentials, "verify", lambda value, transport=None: True
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        a = Project(name="A", organization_id="org_a")
        b = Project(name="B", organization_id="org_b")
        session.add_all([a, b])
        session.commit()

        def override_session():
            yield session

        principal = {"value": admin()}
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[current_principal] = lambda: principal["value"]
        try:
            with TestClient(app) as client:
                yield client, session, principal, a, b
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


ROUTE = "/api/organizations/current/provider-credentials"


def test_admin_saves_key_and_reads_never_return_it(keys):
    client, session, principal, *_ = keys
    response = client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] and body["status"] == "active"
    assert body["redacted_hint"] == "sk-or-v1-…AAAA"
    assert ORG_A_KEY not in response.text
    principal["value"] = member()
    read = client.get(ROUTE)
    assert read.json()["configured"] and ORG_A_KEY not in read.text
    assert read.json()["can_manage"] is False
    record = session.scalar(select(ProviderCredentialRecord))
    assert ORG_A_KEY.encode() not in record.ciphertext
    events = session.scalars(select(ProviderCredentialEvent.event_type)).all()
    assert events == ["created"]


def test_members_cannot_change_keys(keys):
    client, _, principal, *_ = keys
    principal["value"] = member()
    assert (
        client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY}).status_code
        == 403
    )
    assert client.delete(ROUTE + "/openrouter").status_code == 403
    assert client.post(ROUTE + "/openrouter/test").status_code == 403


def test_organizations_are_isolated(keys):
    client, session, principal, a, b = keys
    assert (
        client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY}).status_code
        == 200
    )
    principal["value"] = admin("org_b")
    assert client.get(ROUTE).json()["configured"] is False
    credential, _ = provider_credentials.resolve(session, a.id)
    assert credential.api_key.get_secret_value() == ORG_A_KEY
    # Clerk mode never falls back to the server environment key.
    credential, message = provider_credentials.resolve(session, b.id)
    assert credential is None and "organization admin" in message


def test_rotation_and_deletion_keep_audit_events(keys):
    client, session, *_ = keys
    client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    rotated = client.put(ROUTE + "/openrouter", json={"api_key": ORG_B_KEY})
    assert rotated.json()["redacted_hint"].endswith("BBBB")
    deleted = client.delete(ROUTE + "/openrouter")
    assert deleted.status_code == 200 and deleted.json()["configured"] is False
    assert session.scalar(select(ProviderCredentialRecord)) is None
    events = session.scalars(
        select(ProviderCredentialEvent.event_type).order_by(ProviderCredentialEvent.id)
    ).all()
    assert events == ["created", "rotated", "deleted"]


def test_ciphertext_is_bound_to_its_organization(keys):
    client, session, principal, a, _ = keys
    client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    record = session.scalar(select(ProviderCredentialRecord))
    moved = ProviderCredentialRecord(
        id=record.id,
        scope_key="organization:org_b",
        organization_id="org_b",
        provider="openrouter",
        ciphertext=record.ciphertext,
        nonce=record.nonce,
        wrapped_key=record.wrapped_key,
        wrap_nonce=record.wrap_nonce,
        key_version=record.key_version,
        redacted_hint=record.redacted_hint,
        created_by="x",
        updated_by="x",
    )
    with pytest.raises(ArtifactUnavailableError):
        provider_credentials._decrypt(moved)


def test_rejected_key_blocks_use_until_retested(keys, monkeypatch):
    client, session, _, a, _ = keys
    client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    session.scalar(select(ProviderCredentialRecord)).status = "rejected"
    session.commit()
    credential, message = provider_credentials.resolve(session, a.id)
    assert credential is None and "rejected" in message
    tested = client.post(ROUTE + "/openrouter/test")
    assert tested.json()["status"] == "active"


def test_unverified_key_is_not_stored(keys, monkeypatch):
    client, session, *_ = keys
    monkeypatch.setattr(
        provider_credentials, "verify", lambda value, transport=None: False
    )
    response = client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    assert response.status_code == 422
    assert session.scalar(select(ProviderCredentialRecord)) is None


def test_storage_requires_encryption(keys, monkeypatch):
    client, *_ = keys
    monkeypatch.setattr(settings, "artifact_encryption_enabled", False)
    response = client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    assert response.status_code == 503
    assert client.get(ROUTE).json()["storage_available"] is False


def test_project_binding_sends_organization_key(keys, monkeypatch):
    client, session, _, a, b = keys
    client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    monkeypatch.setattr(generation, "reserve_request", lambda: None)
    seen = []

    def respond(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(
            200,
            json={
                "model": "test/chat",
                "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
            },
        )

    chat = generation.OpenRouterChat(httpx.MockTransport(respond))
    config = dict(model="test/chat", max_tokens=128, temperature=0)
    with provider_credentials.bound_for_project(session, a.id):
        chat.generate([], config)
    assert seen == ["Bearer " + ORG_A_KEY]
    with provider_credentials.bound_for_project(session, b.id):
        with pytest.raises(generation.GenerationError, match="organization admin"):
            chat.generate([], config)
    # Unbound calls fail closed in Clerk mode instead of using the env key.
    with pytest.raises(generation.GenerationError):
        chat.generate([], config)
    assert len(seen) == 1


def test_provider_rejection_marks_key(keys, monkeypatch):
    client, session, _, a, _ = keys
    client.put(ROUTE + "/openrouter", json={"api_key": ORG_A_KEY})
    monkeypatch.setattr(generation, "reserve_request", lambda: None)
    marked = []
    monkeypatch.setattr(provider_credentials, "_mark_rejected", marked.append)
    chat = generation.OpenRouterChat(
        httpx.MockTransport(lambda request: httpx.Response(401))
    )
    with provider_credentials.bound_for_project(session, a.id):
        with pytest.raises(generation.GenerationError):
            chat.generate([], dict(model="test/chat", max_tokens=128, temperature=0))
    assert [c.api_key.get_secret_value() for c in marked] == [ORG_A_KEY]


def test_local_mode_prefers_stored_key_then_environment(
    database, encryption, monkeypatch
):
    engine, _ = database
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("env-secret-key"))
    monkeypatch.setattr(
        provider_credentials, "verify", lambda value, transport=None: True
    )
    owner = Principal(uuid4(), "local-owner", None, "local")
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            project = Project(name="Local")
            session.add(project)
            session.commit()
            credential, _ = provider_credentials.resolve(session, project.id)
            assert credential.api_key.get_secret_value() == "env-secret-key"
            provider_credentials.save(session, owner, SecretStr(ORG_A_KEY))
            credential, _ = provider_credentials.resolve(session, project.id)
            assert credential.api_key.get_secret_value() == ORG_A_KEY
        transaction.rollback()


def test_rate_budget_is_per_key(monkeypatch):
    from unittest.mock import MagicMock

    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.eval.return_value = 1
    monkeypatch.setattr(rate_limit.Redis, "from_url", lambda *a, **kw: connection)
    first = credentials.ProviderCredential(
        SecretStr("k1"), uuid4(), "organization:org_a"
    )
    second = credentials.ProviderCredential(
        SecretStr("k2"), uuid4(), "organization:org_b"
    )
    for credential in (first, second):
        with credentials.use(credential):
            rate_limit.reserve_request()
    budget_keys = [call.args[2] for call in connection.eval.call_args_list]
    assert budget_keys == [
        f"rag:openrouter:{first.credential_id}:requests",
        f"rag:openrouter:{second.credential_id}:requests",
    ]


@pytest.mark.parametrize(
    "status,payload,accepted",
    [
        (200, {"data": {"label": "k"}}, True),
        (200, {"data": {"is_management_key": True}}, False),
        (401, {}, False),
    ],
)
def test_verify_uses_openrouter_key_endpoint(status, payload, accepted):
    seen = []

    def respond(request):
        seen.append((str(request.url), request.headers["authorization"]))
        return httpx.Response(status, json=payload)

    assert (
        provider_credentials.verify(ORG_A_KEY, httpx.MockTransport(respond)) is accepted
    )
    assert seen == [("https://openrouter.ai/api/v1/key", "Bearer " + ORG_A_KEY)]


def test_verify_outage_is_unavailable_not_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        provider_credentials.verify(
            ORG_A_KEY, httpx.MockTransport(lambda request: httpx.Response(500))
        )
    assert error.value.status_code == 503
