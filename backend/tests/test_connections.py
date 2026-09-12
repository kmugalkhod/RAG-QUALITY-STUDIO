import base64
import json
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.connections import ConnectionCheck
from app.core.config import settings
from app.core.connection_secrets import (
    ConnectionKeyring,
    EncryptedSecret,
    SecretConfigurationError,
    SecretDecryptionError,
)
from app.models.connection import SourceConnection, SourceConnectionEvent
from app.services import connections
from test_documents import documents_api  # noqa: F401


KEY_1 = bytes(range(32))
KEY_2 = bytes(reversed(range(32)))


def encoded(value):
    return SecretStr(base64.b64encode(value).decode())


@pytest.fixture
def connections_api(documents_api, monkeypatch):  # noqa: F811
    client, engine, project_id, other_project_id = documents_api
    monkeypatch.setattr(settings, "source_connections_enabled", True)
    monkeypatch.setattr(settings, "source_connection_active_key", "v1")
    monkeypatch.setattr(settings, "source_connection_keys", {"v1": encoded(KEY_1)})
    return client, engine, project_id, other_project_id


def s3(name="Warehouse", secret="very-secret-value"):
    return {
        "name": name,
        "credentials": {
            "kind": "s3",
            "access_key_id": "AKIATEST1234",
            "secret_access_key": secret,
        },
    }


def test_aes_gcm_round_trip_unique_nonce_aad_tamper_and_configuration():
    project_id, connection_id = uuid4(), uuid4()
    ring = ConnectionKeyring({"v1": KEY_1}, "v1")
    first = ring.encrypt(
        {"kind": "s3", "value": "secret"}, project_id, connection_id, "s3"
    )
    second = ring.encrypt(
        {"kind": "s3", "value": "secret"}, project_id, connection_id, "s3"
    )
    assert len(first.nonce) == 12 and first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext
    assert ring.decrypt(first, project_id, connection_id, "s3")["value"] == "secret"
    with pytest.raises(SecretDecryptionError):
        ring.decrypt(first, uuid4(), connection_id, "s3")
    with pytest.raises(SecretDecryptionError):
        ring.decrypt(
            EncryptedSecret(first.ciphertext, first.nonce, "retired"),
            project_id,
            connection_id,
            "s3",
        )
    with pytest.raises(SecretDecryptionError):
        ring.decrypt(
            EncryptedSecret(first.ciphertext[:-1] + b"x", first.nonce, "v1"),
            project_id,
            connection_id,
            "s3",
        )
    with pytest.raises(SecretConfigurationError):
        ConnectionKeyring({"v1": b"short"}, "v1")


@pytest.mark.parametrize(
    "payload,secret_values,summary",
    [
        (s3(), ["AKIATEST1234", "very-secret-value"], "Access key ••••1234"),
        (
            {
                "name": "Product wiki",
                "credentials": {
                    "kind": "notion",
                    "integration_token": "notion-private",
                },
            },
            ["notion-private"],
            "Integration token ••••vate",
        ),
        (
            {
                "name": "Engineering wiki",
                "credentials": {
                    "kind": "confluence",
                    "site_url": "https://docs.example.com",
                    "email": "reader@example.com",
                    "api_token": "confluence-private",
                },
            },
            ["reader@example.com", "confluence-private"],
            "docs.example.com",
        ),
    ],
)
def test_create_list_redaction_encrypted_storage_and_scope(
    connections_api, payload, secret_values, summary
):
    client, engine, project_id, other_id = connections_api
    route = f"/api/projects/{project_id}/source-connections"
    response = client.post(route, json=payload)
    assert response.status_code == 201, response.text
    value = response.json()
    assert value["status"] == "untested" and summary in value["redacted_summary"]
    exposed = json.dumps(value) + client.get(route).text
    assert all(secret not in exposed for secret in secret_values)
    assert all(word not in exposed for word in ("ciphertext", "nonce", "key_version"))
    assert (
        client.get(
            f"/api/projects/{other_id}/source-connections/{value['id']}"
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/projects/{other_id}/source-connections").json()["total"] == 0
    )
    with Session(engine) as session:
        stored = session.get(SourceConnection, UUID(value["id"]))
        assert stored.key_version == "v1" and len(stored.secret_nonce) == 12
        assert all(
            secret.encode() not in stored.secret_ciphertext for secret in secret_values
        )
        assert all(
            secret not in json.dumps(stored.redacted_metadata)
            for secret in secret_values
        )
        events = session.scalars(
            select(SourceConnectionEvent).where(
                SourceConnectionEvent.connection_id == stored.id
            )
        ).all()
        assert [(event.event_type, event.outcome) for event in events] == [
            ("created", "succeeded")
        ]
        assert all(
            secret not in json.dumps(events[0].safe_metadata)
            for secret in secret_values
        )


def test_connection_test_rotation_rewrap_and_safe_events(connections_api, monkeypatch):
    client, engine, project_id, _ = connections_api
    route = f"/api/projects/{project_id}/source-connections"
    created = client.post(route, json=s3()).json()
    connection_id = UUID(created["id"])
    received = []

    class Tester:
        def check(self, credentials):
            received.append(credentials)
            return ConnectionCheck("succeeded", "ok")

    monkeypatch.setattr(connections, "tester_for", lambda kind: Tester())
    tested = client.post(f"{route}/{connection_id}/test")
    assert tested.status_code == 200 and tested.json()["status"] == "valid"
    assert received[-1]["secret_access_key"] == "very-secret-value"
    with Session(engine) as session:
        before = session.get(SourceConnection, connection_id)
        old_ciphertext, old_nonce = before.secret_ciphertext, before.secret_nonce

    replacement = "rotated-private-value"
    rotated = client.post(
        f"{route}/{connection_id}/rotate", json=s3(secret=replacement)["credentials"]
    )
    # Rotation accepts a credentials envelope, never a connection name.
    assert rotated.status_code == 422
    rotated = client.post(
        f"{route}/{connection_id}/rotate",
        json={"credentials": s3(secret=replacement)["credentials"]},
    )
    assert rotated.status_code == 200 and rotated.json()["status"] == "untested"
    assert replacement not in rotated.text
    client.post(f"{route}/{connection_id}/test")
    assert received[-1]["secret_access_key"] == replacement

    monkeypatch.setattr(settings, "source_connection_active_key", "v2")
    monkeypatch.setattr(
        settings,
        "source_connection_keys",
        {"v1": encoded(KEY_1), "v2": encoded(KEY_2)},
    )
    rewrapped = client.post(f"{route}/{connection_id}/rewrap")
    assert rewrapped.status_code == 200
    with Session(engine) as session:
        stored = session.get(SourceConnection, connection_id)
        assert stored.key_version == "v2"
        assert stored.secret_nonce != old_nonce
        assert stored.secret_ciphertext != old_ciphertext
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceConnectionEvent)
                .where(SourceConnectionEvent.connection_id == connection_id)
            )
            == 5
        )
    client.post(f"{route}/{connection_id}/test")
    assert received[-1]["secret_access_key"] == replacement


def test_unavailable_and_exception_are_sanitized(connections_api, monkeypatch):
    client, _, project_id, _ = connections_api
    route = f"/api/projects/{project_id}/source-connections"
    created = client.post(route, json=s3(secret="never-expose-this")).json()
    unavailable = client.post(f"{route}/{created['id']}/test")
    assert unavailable.json()["status"] == "unavailable"
    assert "until this connector is installed" in unavailable.json()["last_error"]

    class Broken:
        def check(self, credentials):
            raise RuntimeError(f"provider echoed {credentials['secret_access_key']}")

    monkeypatch.setattr(connections, "tester_for", lambda kind: Broken())
    failed = client.post(f"{route}/{created['id']}/test")
    assert failed.status_code == 200 and failed.json()["status"] == "invalid"
    assert "never-expose-this" not in failed.text
    assert failed.json()["last_error"].startswith("The connection check failed safely")


def test_tamper_unknown_key_validation_and_local_authorization(connections_api):
    client, engine, project_id, _ = connections_api
    route = f"/api/projects/{project_id}/source-connections"
    secret = "validation-private-value"
    bad = client.post(
        route,
        json={
            "name": "Invalid",
            "credentials": {
                "kind": "s3",
                "access_key_id": "id",
                "secret_access_key": secret,
                "extra": secret,
            },
        },
    )
    assert bad.status_code == 422 and secret not in bad.text
    created = client.post(route, json=s3()).json()
    with Session(engine) as session:
        stored = session.get(SourceConnection, UUID(created["id"]))
        stored.secret_ciphertext = stored.secret_ciphertext[:-1] + bytes(
            [stored.secret_ciphertext[-1] ^ 1]
        )
        session.commit()
    tampered = client.post(f"{route}/{created['id']}/test")
    assert tampered.status_code == 503
    assert tampered.json() == {
        "detail": "Stored connection credentials are unavailable."
    }
    public = client.get(route, headers={"host": "public.example"})
    assert public.status_code == 403
    setting = client.get(f"{route}/settings", headers={"host": "public.example"})
    assert setting.status_code == 200 and setting.json()["enabled"] is False


def test_disabled_or_invalid_key_configuration_fails_closed(
    documents_api,  # noqa: F811
    monkeypatch,
):
    client, _, project_id, _ = documents_api
    route = f"/api/projects/{project_id}/source-connections"
    monkeypatch.setattr(settings, "source_connections_enabled", False)
    monkeypatch.setattr(settings, "source_connection_active_key", "")
    monkeypatch.setattr(settings, "source_connection_keys", {})
    assert client.get(f"{route}/settings").json()["enabled"] is False
    assert client.get(route).status_code == 503
    monkeypatch.setattr(settings, "source_connections_enabled", True)
    monkeypatch.setattr(settings, "source_connection_active_key", "v1")
    monkeypatch.setattr(settings, "source_connection_keys", {"v1": SecretStr("bad")})
    assert client.post(route, json=s3()).status_code == 503
