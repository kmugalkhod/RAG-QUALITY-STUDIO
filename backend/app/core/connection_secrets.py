"""AES-256-GCM envelope boundary for source-connection credentials."""

import base64
import binascii
import json
import os
import re
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings


KEY_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


class SecretConfigurationError(RuntimeError):
    pass


class SecretDecryptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: bytes
    nonce: bytes
    key_version: str
    schema_version: int = 1


class ConnectionKeyring:
    def __init__(self, keys: dict[str, bytes], active_version: str):
        if not KEY_VERSION.fullmatch(active_version) or active_version not in keys:
            raise SecretConfigurationError(
                "Source connection encryption is not configured correctly."
            )
        if any(not KEY_VERSION.fullmatch(version) for version in keys):
            raise SecretConfigurationError(
                "Source connection encryption is not configured correctly."
            )
        if any(len(key) != 32 for key in keys.values()):
            raise SecretConfigurationError(
                "Source connection encryption is not configured correctly."
            )
        self._keys = dict(keys)
        self.active_version = active_version

    @classmethod
    def from_settings(cls, config: Settings) -> "ConnectionKeyring":
        decoded: dict[str, bytes] = {}
        try:
            for version, value in config.source_connection_keys.items():
                decoded[version] = base64.b64decode(
                    value.get_secret_value(), validate=True
                )
        except (ValueError, binascii.Error):
            raise SecretConfigurationError(
                "Source connection encryption is not configured correctly."
            ) from None
        return cls(decoded, config.source_connection_active_key)

    @staticmethod
    def _aad(project_id: UUID, connection_id: UUID, kind: str, schema_version: int):
        return (
            f"rag-quality-studio/source-connection/v{schema_version}/"
            f"{project_id}/{connection_id}/{kind}"
        ).encode()

    def encrypt(
        self,
        value: dict,
        project_id: UUID,
        connection_id: UUID,
        kind: str,
    ) -> EncryptedSecret:
        nonce = os.urandom(12)
        plaintext = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        ciphertext = AESGCM(self._keys[self.active_version]).encrypt(
            nonce,
            plaintext,
            self._aad(project_id, connection_id, kind, 1),
        )
        return EncryptedSecret(ciphertext, nonce, self.active_version)

    def decrypt(
        self,
        secret: EncryptedSecret,
        project_id: UUID,
        connection_id: UUID,
        kind: str,
    ) -> dict:
        key = self._keys.get(secret.key_version)
        if key is None or secret.schema_version != 1:
            raise SecretDecryptionError(
                "Stored connection credentials are unavailable."
            )
        try:
            plaintext = AESGCM(key).decrypt(
                secret.nonce,
                secret.ciphertext,
                self._aad(project_id, connection_id, kind, secret.schema_version),
            )
            value = json.loads(plaintext)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise SecretDecryptionError(
                "Stored connection credentials are unavailable."
            ) from None
