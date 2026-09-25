"""Envelope encryption for retained raw artifacts and protected derivation text."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.core.connection_secrets import KEY_VERSION


class ArtifactConfigurationError(RuntimeError):
    pass


class ArtifactUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactEnvelope:
    ciphertext: bytes
    wrapped_key: bytes
    wrap_nonce: bytes
    content_nonce: bytes
    key_version: str
    schema_version: int = 1


class ArtifactKeyring:
    """Local envelope-key implementation behind the deployment key boundary."""

    def __init__(self, keys: dict[str, bytes], active_version: str):
        if not KEY_VERSION.fullmatch(active_version) or active_version not in keys:
            raise ArtifactConfigurationError(
                "Raw-artifact encryption is not configured correctly."
            )
        if any(not KEY_VERSION.fullmatch(version) for version in keys):
            raise ArtifactConfigurationError(
                "Raw-artifact encryption is not configured correctly."
            )
        if any(len(key) != 32 for key in keys.values()):
            raise ArtifactConfigurationError(
                "Raw-artifact encryption is not configured correctly."
            )
        self._keys = dict(keys)
        self.active_version = active_version

    @classmethod
    def from_settings(cls, config: Settings) -> "ArtifactKeyring":
        if not config.artifact_encryption_enabled:
            raise ArtifactConfigurationError("Raw-artifact encryption is disabled.")
        if config.artifact_encryption_mode == "kms":
            return KmsArtifactKeyring.from_settings(config)
        if config.artifact_encryption_mode == "vault":
            return VaultArtifactKeyring.from_settings(config)
        decoded: dict[str, bytes] = {}
        try:
            for version, value in config.artifact_keys.items():
                decoded[version] = base64.b64decode(
                    value.get_secret_value(), validate=True
                )
        except (ValueError, binascii.Error):
            raise ArtifactConfigurationError(
                "Raw-artifact encryption is not configured correctly."
            ) from None
        return cls(decoded, config.artifact_active_key)

    def _wrap_data_key(self, data_key: bytes, aad: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return (
            AESGCM(self._keys[self.active_version]).encrypt(nonce, data_key, aad),
            nonce,
        )

    def _unwrap_data_key(
        self, wrapped_key: bytes, wrap_nonce: bytes, key_version: str, aad: bytes
    ) -> bytes:
        key = self._keys.get(key_version)
        if key is None:
            raise ArtifactUnavailableError("Protected content is unavailable.")
        try:
            value = AESGCM(key).decrypt(wrap_nonce, wrapped_key, aad)
            if len(value) != 32:
                raise ValueError
            return value
        except (InvalidTag, ValueError):
            raise ArtifactUnavailableError(
                "Protected content is unavailable."
            ) from None

    @staticmethod
    def _aad(
        purpose: str,
        project_id: UUID,
        document_id: UUID,
        schema_version: int,
        context: str = "",
    ) -> bytes:
        return (
            f"rag-quality-studio/raw-artifact/v{schema_version}/"
            f"{purpose}/{project_id}/{document_id}/{context}"
        ).encode()

    @staticmethod
    def _object_aad(
        purpose: str,
        object_kind: str,
        project_id: UUID,
        object_id: UUID,
        schema_version: int,
        context: str = "",
    ) -> bytes:
        return (
            f"rag-quality-studio/protected-object/v{schema_version}/"
            f"{object_kind}/{purpose}/{project_id}/{object_id}/{context}"
        ).encode()

    def create_object_key(
        self, *, object_kind: str, project_id: UUID, object_id: UUID
    ) -> tuple[bytes, bytes, bytes, str]:
        data_key = os.urandom(32)
        wrapped_key, wrap_nonce = self._wrap_data_key(
            data_key,
            self._object_aad("data-key", object_kind, project_id, object_id, 1),
        )
        return data_key, wrapped_key, wrap_nonce, self.active_version

    def unwrap_object_key(
        self,
        *,
        object_kind: str,
        wrapped_key: bytes,
        wrap_nonce: bytes,
        key_version: str,
        schema_version: int,
        project_id: UUID,
        object_id: UUID,
    ) -> bytes:
        if schema_version != 1:
            raise ArtifactUnavailableError("Protected content is unavailable.")
        return self._unwrap_data_key(
            wrapped_key,
            wrap_nonce,
            key_version,
            self._object_aad(
                "data-key", object_kind, project_id, object_id, schema_version
            ),
        )

    def encrypt_object_payload(
        self,
        data_key: bytes,
        content: bytes,
        *,
        object_kind: str,
        project_id: UUID,
        object_id: UUID,
        context: str,
    ) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        ciphertext = AESGCM(data_key).encrypt(
            nonce,
            content,
            self._object_aad("payload", object_kind, project_id, object_id, 1, context),
        )
        return ciphertext, nonce

    def decrypt_object_payload(
        self,
        data_key: bytes,
        ciphertext: bytes,
        nonce: bytes,
        *,
        object_kind: str,
        project_id: UUID,
        object_id: UUID,
        context: str,
    ) -> bytes:
        try:
            return AESGCM(data_key).decrypt(
                nonce,
                ciphertext,
                self._object_aad(
                    "payload", object_kind, project_id, object_id, 1, context
                ),
            )
        except InvalidTag:
            raise ArtifactUnavailableError(
                "Protected content is unavailable."
            ) from None

    def encrypt(
        self, content: bytes, project_id: UUID, document_id: UUID
    ) -> ArtifactEnvelope:
        data_key = os.urandom(32)
        content_nonce = os.urandom(12)
        ciphertext = AESGCM(data_key).encrypt(
            content_nonce,
            content,
            self._aad("content", project_id, document_id, 1),
        )
        wrapped_key, wrap_nonce = self._wrap_data_key(
            data_key,
            self._aad("data-key", project_id, document_id, 1),
        )
        return ArtifactEnvelope(
            ciphertext=ciphertext,
            wrapped_key=wrapped_key,
            wrap_nonce=wrap_nonce,
            content_nonce=content_nonce,
            key_version=self.active_version,
        )

    def unwrap_key(
        self,
        *,
        wrapped_key: bytes,
        wrap_nonce: bytes,
        key_version: str,
        schema_version: int,
        project_id: UUID,
        document_id: UUID,
    ) -> bytes:
        if schema_version != 1:
            raise ArtifactUnavailableError("The retained raw artifact is unavailable.")
        try:
            return self._unwrap_data_key(
                wrapped_key,
                wrap_nonce,
                key_version,
                self._aad("data-key", project_id, document_id, schema_version),
            )
        except ArtifactUnavailableError:
            raise ArtifactUnavailableError(
                "The retained raw artifact is unavailable."
            ) from None

    def decrypt(
        self,
        *,
        ciphertext: bytes,
        wrapped_key: bytes,
        wrap_nonce: bytes,
        content_nonce: bytes,
        key_version: str,
        schema_version: int,
        project_id: UUID,
        document_id: UUID,
    ) -> bytes:
        data_key = self.unwrap_key(
            wrapped_key=wrapped_key,
            wrap_nonce=wrap_nonce,
            key_version=key_version,
            schema_version=schema_version,
            project_id=project_id,
            document_id=document_id,
        )
        try:
            return AESGCM(data_key).decrypt(
                content_nonce,
                ciphertext,
                self._aad("content", project_id, document_id, schema_version),
            )
        except InvalidTag:
            raise ArtifactUnavailableError(
                "The retained raw artifact is unavailable."
            ) from None

    def rewrap_artifact_key(
        self,
        *,
        wrapped_key: bytes,
        wrap_nonce: bytes,
        key_version: str,
        schema_version: int,
        project_id: UUID,
        document_id: UUID,
    ) -> tuple[bytes, bytes, str]:
        if schema_version != 1:
            raise ArtifactUnavailableError("The retained raw artifact is unavailable.")
        aad = self._aad("data-key", project_id, document_id, schema_version)
        data_key = self._unwrap_data_key(wrapped_key, wrap_nonce, key_version, aad)
        updated, nonce = self._wrap_data_key(data_key, aad)
        return updated, nonce, self.active_version

    def encrypt_protected_text(
        self,
        data_key: bytes,
        text: str,
        *,
        project_id: UUID,
        document_id: UUID,
        context: str,
    ) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return (
            AESGCM(data_key).encrypt(
                nonce,
                text.encode("utf-8"),
                self._aad("protected-text", project_id, document_id, 1, context),
            ),
            nonce,
        )

    def decrypt_protected_text(
        self,
        data_key: bytes,
        ciphertext: bytes,
        nonce: bytes,
        *,
        project_id: UUID,
        document_id: UUID,
        context: str,
    ) -> str:
        try:
            return (
                AESGCM(data_key)
                .decrypt(
                    nonce,
                    ciphertext,
                    self._aad("protected-text", project_id, document_id, 1, context),
                )
                .decode("utf-8")
            )
        except (InvalidTag, UnicodeDecodeError):
            raise ArtifactUnavailableError(
                "Protected source text is unavailable."
            ) from None


def _external_references(config: Settings) -> tuple[dict[str, str], str]:
    references = dict(config.artifact_key_references)
    active = config.artifact_active_key
    if (
        not KEY_VERSION.fullmatch(active)
        or active not in references
        or any(not KEY_VERSION.fullmatch(version) for version in references)
        or any(not value.strip() or len(value) > 2048 for value in references.values())
    ):
        raise ArtifactConfigurationError(
            "Raw-artifact encryption is not configured correctly."
        )
    return references, active


class KmsArtifactKeyring(ArtifactKeyring):
    """AWS KMS envelope wrapper using ambient IAM credentials and encryption context."""

    marker = b"aws-kms-v1"

    def __init__(self, client, references: dict[str, str], active_version: str):
        self._client = client
        self._references = references
        self.active_version = active_version
        self._keys = {}

    @classmethod
    def from_settings(cls, config: Settings):
        references, active = _external_references(config)
        try:
            import boto3

            options = {}
            if config.artifact_kms_region:
                options["region_name"] = config.artifact_kms_region
            if config.artifact_kms_endpoint_url:
                endpoint = urlsplit(config.artifact_kms_endpoint_url)
                if endpoint.scheme != "https" or not endpoint.hostname:
                    raise ValueError
                options["endpoint_url"] = config.artifact_kms_endpoint_url
            client = boto3.client("kms", **options)
        except Exception:
            raise ArtifactConfigurationError(
                "Raw-artifact KMS is not configured correctly."
            ) from None
        return cls(client, references, active)

    @staticmethod
    def _context(aad: bytes) -> dict[str, str]:
        return {"rag-aad-sha256": hashlib.sha256(aad).hexdigest()}

    def _wrap_data_key(self, data_key: bytes, aad: bytes) -> tuple[bytes, bytes]:
        try:
            result = self._client.encrypt(
                KeyId=self._references[self.active_version],
                Plaintext=data_key,
                EncryptionContext=self._context(aad),
            )
            wrapped = bytes(result["CiphertextBlob"])
            if not wrapped:
                raise ValueError
            return wrapped, self.marker
        except Exception:
            raise ArtifactUnavailableError(
                "The raw-artifact key provider is unavailable."
            ) from None

    def _unwrap_data_key(
        self, wrapped_key: bytes, wrap_nonce: bytes, key_version: str, aad: bytes
    ) -> bytes:
        reference = self._references.get(key_version)
        if reference is None or wrap_nonce != self.marker:
            raise ArtifactUnavailableError("Protected content is unavailable.")
        try:
            result = self._client.decrypt(
                KeyId=reference,
                CiphertextBlob=wrapped_key,
                EncryptionContext=self._context(aad),
            )
            value = bytes(result["Plaintext"])
            if len(value) != 32:
                raise ValueError
            return value
        except Exception:
            raise ArtifactUnavailableError(
                "Protected content is unavailable."
            ) from None


class VaultArtifactKeyring(ArtifactKeyring):
    """Vault Transit envelope wrapper; Vault never receives source content."""

    marker = b"vault-transit-v1"
    _path_part = re.compile(r"[A-Za-z0-9_.-]{1,128}")

    def __init__(
        self,
        address: str,
        token: str,
        mount: str,
        references: dict[str, str],
        active_version: str,
    ):
        self._address = address.rstrip("/")
        self._token = token
        self._mount = mount
        self._references = references
        self.active_version = active_version
        self._keys = {}

    @classmethod
    def from_settings(cls, config: Settings):
        references, active = _external_references(config)
        parsed = urlsplit(config.artifact_vault_address)
        token = config.artifact_vault_token.get_secret_value()
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or not token
            or len(token) > 4096
            or not cls._path_part.fullmatch(config.artifact_vault_mount)
            or any(not cls._path_part.fullmatch(value) for value in references.values())
        ):
            raise ArtifactConfigurationError(
                "Raw-artifact Vault Transit is not configured correctly."
            )
        return cls(
            config.artifact_vault_address,
            token,
            config.artifact_vault_mount,
            references,
            active,
        )

    def _request(self, action: str, key: str, payload: dict) -> dict:
        try:
            response = httpx.post(
                f"{self._address}/v1/{quote(self._mount)}/{action}/{quote(key)}",
                headers={"X-Vault-Token": self._token},
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            value = response.json()["data"]
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            raise ArtifactUnavailableError(
                "The raw-artifact key provider is unavailable."
            ) from None

    @staticmethod
    def _associated_data(aad: bytes) -> str:
        return base64.b64encode(aad).decode("ascii")

    def _wrap_data_key(self, data_key: bytes, aad: bytes) -> tuple[bytes, bytes]:
        result = self._request(
            "encrypt",
            self._references[self.active_version],
            {
                "plaintext": base64.b64encode(data_key).decode("ascii"),
                "associated_data": self._associated_data(aad),
            },
        )
        ciphertext = result.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext.startswith("vault:v"):
            raise ArtifactUnavailableError(
                "The raw-artifact key provider is unavailable."
            )
        return ciphertext.encode("utf-8"), self.marker

    def _unwrap_data_key(
        self, wrapped_key: bytes, wrap_nonce: bytes, key_version: str, aad: bytes
    ) -> bytes:
        reference = self._references.get(key_version)
        if reference is None or wrap_nonce != self.marker:
            raise ArtifactUnavailableError("Protected content is unavailable.")
        try:
            ciphertext = wrapped_key.decode("utf-8")
        except UnicodeDecodeError:
            raise ArtifactUnavailableError(
                "Protected content is unavailable."
            ) from None
        result = self._request(
            "decrypt",
            reference,
            {
                "ciphertext": ciphertext,
                "associated_data": self._associated_data(aad),
            },
        )
        plaintext = result.get("plaintext")
        try:
            value = base64.b64decode(plaintext, validate=True)
        except (TypeError, ValueError, binascii.Error):
            raise ArtifactUnavailableError(
                "Protected content is unavailable."
            ) from None
        if len(value) != 32:
            raise ArtifactUnavailableError("Protected content is unavailable.")
        return value
