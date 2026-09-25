"""Synthetic artifact encryption and retention-boundary tests."""

import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.artifact_crypto import (
    ArtifactConfigurationError,
    ArtifactKeyring,
    ArtifactUnavailableError,
    KmsArtifactKeyring,
    VaultArtifactKeyring,
)
from app.core.config import Settings, settings
from app.core.auth import validate_security_configuration
from app.services import artifact_storage


def _keyring():
    return ArtifactKeyring({"test-v1": bytes(range(32))}, "test-v1")


def test_artifact_envelope_round_trip_uses_unique_data_keys_and_nonces():
    keyring = _keyring()
    project_id, document_id = uuid4(), uuid4()
    first = keyring.encrypt(b"synthetic raw content", project_id, document_id)
    second = keyring.encrypt(b"synthetic raw content", project_id, document_id)
    assert first.ciphertext != second.ciphertext
    assert first.wrapped_key != second.wrapped_key
    assert first.content_nonce != second.content_nonce
    assert first.wrap_nonce != second.wrap_nonce
    assert (
        keyring.decrypt(
            ciphertext=first.ciphertext,
            wrapped_key=first.wrapped_key,
            wrap_nonce=first.wrap_nonce,
            content_nonce=first.content_nonce,
            key_version=first.key_version,
            schema_version=first.schema_version,
            project_id=project_id,
            document_id=document_id,
        )
        == b"synthetic raw content"
    )


def test_artifact_envelope_rejects_tamper_and_cross_document_copy():
    keyring = _keyring()
    project_id, document_id = uuid4(), uuid4()
    envelope = keyring.encrypt(b"synthetic raw content", project_id, document_id)
    with pytest.raises(ArtifactUnavailableError):
        keyring.decrypt(
            ciphertext=envelope.ciphertext[:-1] + bytes([envelope.ciphertext[-1] ^ 1]),
            wrapped_key=envelope.wrapped_key,
            wrap_nonce=envelope.wrap_nonce,
            content_nonce=envelope.content_nonce,
            key_version=envelope.key_version,
            schema_version=envelope.schema_version,
            project_id=project_id,
            document_id=document_id,
        )
    with pytest.raises(ArtifactUnavailableError):
        keyring.decrypt(
            ciphertext=envelope.ciphertext,
            wrapped_key=envelope.wrapped_key,
            wrap_nonce=envelope.wrap_nonce,
            content_nonce=envelope.content_nonce,
            key_version=envelope.key_version,
            schema_version=envelope.schema_version,
            project_id=project_id,
            document_id=uuid4(),
        )


def test_artifact_data_key_can_be_rewrapped_without_rewriting_ciphertext():
    project_id, document_id = uuid4(), uuid4()
    original = ArtifactKeyring({"old-v1": bytes(range(32))}, "old-v1")
    envelope = original.encrypt(b"synthetic rotation content", project_id, document_id)
    rotating = ArtifactKeyring(
        {"old-v1": bytes(range(32)), "new-v2": bytes(reversed(range(32)))},
        "new-v2",
    )
    wrapped, nonce, version = rotating.rewrap_artifact_key(
        wrapped_key=envelope.wrapped_key,
        wrap_nonce=envelope.wrap_nonce,
        key_version=envelope.key_version,
        schema_version=envelope.schema_version,
        project_id=project_id,
        document_id=document_id,
    )
    replacement_only = ArtifactKeyring({"new-v2": bytes(reversed(range(32)))}, "new-v2")
    assert version == "new-v2"
    assert (
        replacement_only.decrypt(
            ciphertext=envelope.ciphertext,
            wrapped_key=wrapped,
            wrap_nonce=nonce,
            content_nonce=envelope.content_nonce,
            key_version=version,
            schema_version=envelope.schema_version,
            project_id=project_id,
            document_id=document_id,
        )
        == b"synthetic rotation content"
    )


def test_settings_fail_closed_for_missing_or_malformed_keys():
    with pytest.raises(ArtifactConfigurationError):
        ArtifactKeyring.from_settings(Settings(artifact_encryption_enabled=True))
    with pytest.raises(ArtifactConfigurationError):
        ArtifactKeyring.from_settings(
            Settings(
                artifact_encryption_enabled=True,
                artifact_active_key="test-v1",
                artifact_keys={"test-v1": SecretStr("not-base64")},
            )
        )


class _KmsDouble:
    def __init__(self):
        self.values = {}

    def encrypt(self, *, KeyId, Plaintext, EncryptionContext):
        ciphertext = b"kms:" + bytes([len(self.values)]) + Plaintext[::-1]
        self.values[ciphertext] = (KeyId, Plaintext, EncryptionContext)
        return {"CiphertextBlob": ciphertext}

    def decrypt(self, *, KeyId, CiphertextBlob, EncryptionContext):
        stored_key, plaintext, context = self.values[CiphertextBlob]
        if stored_key != KeyId or context != EncryptionContext:
            raise ValueError
        return {"Plaintext": plaintext}


def test_shared_auth_requires_configured_external_artifact_boundary(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "auth_oidc_issuer", "https://issuer.example")
    monkeypatch.setattr(settings, "auth_oidc_audience", "rag-studio")
    monkeypatch.setattr(
        settings, "auth_oidc_jwks_url", "https://issuer.example/.well-known/jwks.json"
    )
    monkeypatch.setattr(settings, "artifact_encryption_enabled", False)
    with pytest.raises(RuntimeError, match="encrypted raw-artifact"):
        validate_security_configuration()

    monkeypatch.setattr(settings, "artifact_encryption_enabled", True)
    monkeypatch.setattr(settings, "artifact_encryption_mode", "local-keyring")
    with pytest.raises(RuntimeError, match="KMS or Vault"):
        validate_security_configuration()

    monkeypatch.setattr(settings, "artifact_encryption_mode", "kms")
    monkeypatch.setattr(settings, "artifact_active_key", "kms-v1")
    monkeypatch.setattr(
        settings, "artifact_key_references", {"kms-v1": "alias/rag-artifacts"}
    )
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: _KmsDouble())
    validate_security_configuration()


def test_kms_wrapper_binds_data_key_to_artifact_context():
    keyring = KmsArtifactKeyring(_KmsDouble(), {"kms-v1": "alias/rag"}, "kms-v1")
    project_id, document_id = uuid4(), uuid4()
    envelope = keyring.encrypt(b"synthetic KMS content", project_id, document_id)
    assert (
        keyring.decrypt(
            ciphertext=envelope.ciphertext,
            wrapped_key=envelope.wrapped_key,
            wrap_nonce=envelope.wrap_nonce,
            content_nonce=envelope.content_nonce,
            key_version=envelope.key_version,
            schema_version=envelope.schema_version,
            project_id=project_id,
            document_id=document_id,
        )
        == b"synthetic KMS content"
    )
    with pytest.raises(ArtifactUnavailableError):
        keyring.decrypt(
            ciphertext=envelope.ciphertext,
            wrapped_key=envelope.wrapped_key,
            wrap_nonce=envelope.wrap_nonce,
            content_nonce=envelope.content_nonce,
            key_version=envelope.key_version,
            schema_version=envelope.schema_version,
            project_id=project_id,
            document_id=uuid4(),
        )


def test_vault_transit_wrapper_uses_associated_data(monkeypatch):
    saved = {}

    def vault_request(url, *, headers, json, timeout):
        assert headers == {"X-Vault-Token": "synthetic-token"}
        assert timeout == 10
        request = __import__("httpx").Request("POST", url)
        if "/encrypt/" in url:
            ciphertext = f"vault:v1:{len(saved)}"
            saved[ciphertext] = (json["plaintext"], json["associated_data"])
            payload = {"data": {"ciphertext": ciphertext}}
        else:
            plaintext, associated_data = saved[json["ciphertext"]]
            assert associated_data == json["associated_data"]
            payload = {"data": {"plaintext": plaintext}}
        return __import__("httpx").Response(200, json=payload, request=request)

    monkeypatch.setattr("app.core.artifact_crypto.httpx.post", vault_request)
    keyring = VaultArtifactKeyring(
        "https://vault.example",
        "synthetic-token",
        "transit",
        {"vault-v1": "rag-artifacts"},
        "vault-v1",
    )
    project_id, document_id = uuid4(), uuid4()
    envelope = keyring.encrypt(b"synthetic Vault content", project_id, document_id)
    assert (
        keyring.decrypt(
            ciphertext=envelope.ciphertext,
            wrapped_key=envelope.wrapped_key,
            wrap_nonce=envelope.wrap_nonce,
            content_nonce=envelope.content_nonce,
            key_version=envelope.key_version,
            schema_version=envelope.schema_version,
            project_id=project_id,
            document_id=document_id,
        )
        == b"synthetic Vault content"
    )


def test_storage_writes_ciphertext_and_materializes_bounded_plaintext(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "storage_path", tmp_path)
    monkeypatch.setattr(settings, "artifact_encryption_enabled", True)
    monkeypatch.setattr(settings, "artifact_active_key", "test-v1")
    monkeypatch.setattr(
        settings,
        "artifact_keys",
        {"test-v1": SecretStr(base64.b64encode(bytes(range(32))).decode())},
    )
    monkeypatch.setattr(settings, "artifact_retention_days", 30)
    project_id, document_id = uuid4(), uuid4()
    stored = artifact_storage.store(b"synthetic raw content", project_id, document_id)
    assert stored.path.read_bytes() != b"synthetic raw content"
    assert stored.state == "encrypted"
    assert stored.retained_until is not None

    document = SimpleNamespace(
        id=document_id,
        project_id=project_id,
        storage_name=stored.storage_name,
        artifact_state=stored.state,
        artifact_encryption_schema=stored.envelope.schema_version,
        artifact_key_version=stored.envelope.key_version,
        artifact_wrapped_key=stored.envelope.wrapped_key,
        artifact_wrap_nonce=stored.envelope.wrap_nonce,
        artifact_content_nonce=stored.envelope.content_nonce,
    )

    with artifact_storage.materialize(document) as path:
        assert path.read_bytes() == b"synthetic raw content"
        materialized = path
    assert not materialized.exists()
