"""Organization-scoped OpenRouter keys, encrypted with the artifact key boundary."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.artifact_crypto import ArtifactConfigurationError, ArtifactKeyring
from app.core.auth import Principal
from app.core.config import settings
from app.models.project import Project
from app.models.provider_credential import (
    ProviderCredentialEvent,
    ProviderCredentialRecord,
)
from app.providers import credentials
from app.providers.credentials import ProviderCredential
from app.schemas.provider_credential import ProviderKeyRead

logger = logging.getLogger(__name__)
PROVIDER = "openrouter"
OBJECT_KIND = "provider-credential"
KEY_URL = "https://openrouter.ai/api/v1/key"
REJECTED_ORGANIZATION = (
    "OpenRouter rejected this organization's key. "
    "Ask an organization admin to replace it in Organization settings."
)


def now():
    return datetime.now(UTC)


def principal_scope(principal: Principal) -> tuple[str, str | None]:
    if principal.auth_mode == "clerk":
        if not principal.organization_id:
            raise HTTPException(403, "Select an organization to continue.")
        org = principal.organization_id
        return f"organization:{org}", org
    if principal.auth_mode == "local":
        return "instance", None
    # OIDC deployments have no organization; the operator manages the key.
    raise HTTPException(404, "Stored provider keys are unavailable in this mode.")


def project_scope(session: Session, project_id: UUID) -> str | None:
    if settings.auth_mode == "clerk":
        org = session.scalar(
            select(Project.organization_id).where(Project.id == project_id)
        )
        return f"organization:{org}" if org else None
    if settings.auth_mode == "local":
        return "instance"
    return None


def can_manage(principal: Principal) -> bool:
    if principal.auth_mode == "clerk":
        return principal.organization_role == "org:admin"
    return principal.auth_mode == "local"


def _require_manager(principal: Principal):
    if not can_manage(principal):
        raise HTTPException(403, "Organization admin access is required.")


def _keyring() -> ArtifactKeyring:
    try:
        return ArtifactKeyring.from_settings(settings)
    except ArtifactConfigurationError:
        raise HTTPException(
            503,
            "Encrypted key storage is unavailable. Enable artifact encryption on the server.",
        ) from None


def _storage_available() -> bool:
    try:
        ArtifactKeyring.from_settings(settings)
        return True
    except ArtifactConfigurationError:
        return False


def _aad_scope(scope_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"rag-quality-studio/provider-scope/{scope_key}")


def _hint(value: str) -> str:
    prefix = "sk-or-v1-" if value.startswith("sk-or-v1-") else ""
    return f"{prefix}…{value[-4:]}"


def _event(session, record_scope, credential_id, event_type, outcome, actor):
    session.add(
        ProviderCredentialEvent(
            scope_key=record_scope,
            credential_id=credential_id,
            provider=PROVIDER,
            event_type=event_type,
            outcome=outcome,
            actor=actor,
        )
    )


def verify(api_key: str, transport=None) -> bool:
    """True when OpenRouter accepts the key for inference; False when rejected."""
    try:
        with httpx.Client(
            timeout=httpx.Timeout(10, connect=5),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.get(
                KEY_URL, headers={"Authorization": "Bearer " + api_key}
            )
            if response.status_code in (401, 403):
                return False
            if response.status_code != 200 or len(response.content) > 100_000:
                raise ValueError()
            data = response.json()["data"]
            if not isinstance(data, dict):
                raise ValueError()
            # Management/provisioning keys cannot call inference endpoints.
            return not (
                data.get("is_management_key") or data.get("is_provisioning_key")
            )
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(
            503, "OpenRouter could not verify the key right now. Retry shortly."
        ) from None


def _record(session, scope_key, *, lock=False):
    query = select(ProviderCredentialRecord).where(
        ProviderCredentialRecord.scope_key == scope_key,
        ProviderCredentialRecord.provider == PROVIDER,
    )
    if lock:
        query = query.with_for_update()
    return session.scalar(query)


def _decrypt(record: ProviderCredentialRecord) -> SecretStr:
    keyring = ArtifactKeyring.from_settings(settings)
    scope = _aad_scope(record.scope_key)
    data_key = keyring.unwrap_object_key(
        object_kind=OBJECT_KIND,
        wrapped_key=record.wrapped_key,
        wrap_nonce=record.wrap_nonce,
        key_version=record.key_version,
        schema_version=record.schema_version,
        project_id=scope,
        object_id=record.id,
    )
    plain = keyring.decrypt_object_payload(
        data_key,
        record.ciphertext,
        record.nonce,
        object_kind=OBJECT_KIND,
        project_id=scope,
        object_id=record.id,
        context=record.provider,
    )
    return SecretStr(plain.decode("utf-8"))


def read(session: Session, principal: Principal) -> ProviderKeyRead:
    scope_key, _ = principal_scope(principal)
    record = _record(session, scope_key)
    return ProviderKeyRead(
        scope="instance" if scope_key == "instance" else "organization",
        configured=record is not None,
        status=record.status if record else None,
        redacted_hint=record.redacted_hint if record else None,
        updated_by=record.updated_by if record else None,
        updated_at=record.updated_at if record else None,
        last_verified_at=record.last_verified_at if record else None,
        environment_fallback=record is None
        and credentials.environment_credential() is not None,
        can_manage=can_manage(principal),
        storage_available=_storage_available(),
    )


def save(
    session: Session, principal: Principal, api_key: SecretStr, transport=None
) -> ProviderKeyRead:
    _require_manager(principal)
    scope_key, organization_id = principal_scope(principal)
    value = api_key.get_secret_value().strip()
    if any(ch.isspace() or not ch.isprintable() for ch in value) or len(value) < 20:
        raise HTTPException(422, "Enter a valid OpenRouter API key.")
    keyring = _keyring()
    if not verify(value, transport):
        raise HTTPException(422, "OpenRouter rejected this key.")
    record = _record(session, scope_key, lock=True)
    created = record is None
    if created:
        record = ProviderCredentialRecord(
            id=uuid4(),
            scope_key=scope_key,
            organization_id=organization_id,
            provider=PROVIDER,
            created_by=principal.subject,
        )
    aad_scope = _aad_scope(scope_key)
    data_key, wrapped_key, wrap_nonce, key_version = keyring.create_object_key(
        object_kind=OBJECT_KIND, project_id=aad_scope, object_id=record.id
    )
    ciphertext, nonce = keyring.encrypt_object_payload(
        data_key,
        value.encode("utf-8"),
        object_kind=OBJECT_KIND,
        project_id=aad_scope,
        object_id=record.id,
        context=PROVIDER,
    )
    current = now()
    record.ciphertext, record.nonce = ciphertext, nonce
    record.wrapped_key, record.wrap_nonce = wrapped_key, wrap_nonce
    record.key_version, record.schema_version = key_version, 1
    record.redacted_hint = _hint(value)
    record.status = "active"
    record.updated_by = principal.subject
    record.updated_at = record.last_verified_at = current
    if not created:
        record.rotated_at = current
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "The key changed concurrently. Retry.") from None
    _event(
        session,
        scope_key,
        record.id,
        "created" if created else "rotated",
        "succeeded",
        principal.subject,
    )
    session.commit()
    return read(session, principal)


def test(session: Session, principal: Principal, transport=None) -> ProviderKeyRead:
    _require_manager(principal)
    scope_key, _ = principal_scope(principal)
    record = _record(session, scope_key, lock=True)
    if record is None:
        raise HTTPException(404, "No OpenRouter key is stored.")
    accepted = verify(_decrypt(record).get_secret_value(), transport)
    record.status = "active" if accepted else "rejected"
    record.last_verified_at = now()
    _event(
        session,
        scope_key,
        record.id,
        "tested",
        "succeeded" if accepted else "failed",
        principal.subject,
    )
    session.commit()
    return read(session, principal)


def delete(session: Session, principal: Principal) -> ProviderKeyRead:
    _require_manager(principal)
    scope_key, _ = principal_scope(principal)
    record = _record(session, scope_key, lock=True)
    if record is None:
        raise HTTPException(404, "No OpenRouter key is stored.")
    _event(session, scope_key, record.id, "deleted", "succeeded", principal.subject)
    session.delete(record)
    session.commit()
    return read(session, principal)


def resolve(
    session: Session, project_id: UUID
) -> tuple[ProviderCredential | None, str]:
    """The key that pays for this project's provider calls, or why none applies."""
    scope_key = project_scope(session, project_id)
    if scope_key is None and settings.auth_mode == "clerk":
        return None, credentials.MISSING_ORGANIZATION
    record = _record(session, scope_key) if scope_key else None
    if record is not None:
        if record.status != "active":
            return None, REJECTED_ORGANIZATION
        return (
            ProviderCredential(_decrypt(record), record.id, scope_key),
            "",
        )
    if settings.auth_mode == "clerk":
        return None, credentials.MISSING_ORGANIZATION
    return credentials.environment_credential(), credentials.MISSING_INSTANCE


def _mark_rejected(credential: ProviderCredential):
    from app.db.session import engine

    with Session(engine) as session:
        result = session.execute(
            update(ProviderCredentialRecord)
            .where(
                ProviderCredentialRecord.id == credential.credential_id,
                ProviderCredentialRecord.status == "active",
            )
            .values(status="rejected", updated_at=now())
        )
        if result.rowcount:
            _event(
                session,
                credential.scope,
                credential.credential_id,
                "rejected_by_provider",
                "failed",
                "system",
            )
        session.commit()


@contextmanager
def bound_for_project(session: Session, project_id: UUID):
    """Bind this project's key and approved chat models for nested provider calls."""
    from app.providers import chat_models as chat_model_context
    from app.services import chat_models

    scope_key = project_scope(session, project_id)
    existing = credentials.bound()
    if existing is not None and existing.scope == scope_key:
        # Nested entry points within one request or job share the binding.
        yield existing
        return
    credential, message = resolve(session, project_id)
    approved = chat_models.approved_for_scope(session, scope_key)
    with (
        chat_model_context.use(approved),
        credentials.use(credential, message, scope_key) as binding,
    ):
        try:
            yield binding
        finally:
            if binding.rejected and credential and credential.credential_id:
                try:
                    _mark_rejected(credential)
                except Exception:
                    # Never mask the provider error with bookkeeping.
                    logger.exception("Could not mark a rejected provider key.")
