"""Local-owner and OIDC authentication with project-role authorization."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_address
from typing import Annotated
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.models.security import ProjectMembership, SensitiveAccessEvent, UserIdentity


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    subject: str
    email: str | None
    auth_mode: str


def validate_security_configuration() -> None:
    if settings.auth_mode != "oidc":
        return
    parsed = urlsplit(settings.auth_oidc_jwks_url)
    if (
        not settings.auth_oidc_issuer.strip()
        or not settings.auth_oidc_audience.strip()
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise RuntimeError("Shared deployment OIDC authentication is not configured.")
    if not settings.artifact_encryption_enabled:
        raise RuntimeError("Shared deployments require encrypted raw-artifact storage.")
    if settings.artifact_encryption_mode == "local-keyring":
        raise RuntimeError(
            "Shared deployments require a KMS or Vault raw-artifact key boundary."
        )
    from app.core.artifact_crypto import ArtifactKeyring

    ArtifactKeyring.from_settings(settings)


def _loopback_request(request: Request) -> bool:
    host = (request.headers.get("host") or "").split(":", 1)[0].strip("[]").lower()
    if host == "testserver":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=300)


def _oidc_claims(request: Request) -> dict:
    issuer = settings.auth_oidc_issuer.rstrip("/")
    audience = settings.auth_oidc_audience
    jwks_url = settings.auth_oidc_jwks_url
    parsed = urlsplit(jwks_url)
    if (
        not issuer
        or not audience
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HTTPException(503, "OIDC authentication is not configured.")
    authorization = request.headers.get("authorization") or ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 16_384:
        raise HTTPException(401, "Authentication is required.")
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=list(settings.auth_oidc_algorithms),
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "The authentication token is invalid.") from None


def _identity(session: Session, subject: str, email: str | None) -> UserIdentity:
    if not subject or len(subject) > 500:
        raise HTTPException(401, "The authentication token is invalid.")
    if email is not None and len(email) > 320:
        email = None
    identity_id = (
        uuid5(NAMESPACE_URL, "rag-quality-studio/local-owner")
        if settings.auth_mode == "local"
        else uuid4()
    )
    statement = (
        insert(UserIdentity)
        .values(id=identity_id, external_subject=subject, email=email)
        .on_conflict_do_update(
            index_elements=[UserIdentity.external_subject],
            set_={"email": email},
        )
        .returning(UserIdentity.id)
    )
    user_id = session.scalar(statement)
    session.flush()
    return session.get(UserIdentity, user_id)


def current_principal(
    request: Request, session: Session = Depends(get_session)
) -> Principal:
    if settings.auth_mode == "local":
        if not _loopback_request(request):
            raise HTTPException(403, "Local authentication is restricted to loopback.")
        subject = settings.auth_local_subject
        email = settings.auth_local_email or None
        return Principal(
            uuid5(NAMESPACE_URL, "rag-quality-studio/local-owner"),
            subject,
            email,
            settings.auth_mode,
        )
    else:
        claims = _oidc_claims(request)
        subject = claims.get("sub")
        email = claims.get("email")
        if not isinstance(subject, str) or (
            email is not None and not isinstance(email, str)
        ):
            raise HTTPException(401, "The authentication token is invalid.")
    identity = _identity(session, subject, email)
    session.commit()
    return Principal(identity.id, subject, email, settings.auth_mode)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_project_access(
    project_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(current_principal),
) -> str:
    role = project_role(session, project_id, principal)
    if role is None:
        # Do not reveal whether a project exists to an unrelated principal.
        raise HTTPException(404, "Project not found.")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and role == "viewer":
        raise HTTPException(403, "This project role has read-only access.")
    return role


def project_role(
    session: Session, project_id: UUID, principal: Principal
) -> str | None:
    if principal.auth_mode == "local":
        return "owner"
    return session.scalar(
        select(ProjectMembership.role).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == principal.user_id,
        )
    )


def audit_sensitive_access(
    session: Session,
    *,
    project_id: UUID,
    principal: Principal,
    action: str,
    resource_kind: str,
    resource_id: UUID | None,
    outcome: str,
):
    # Local mode has no membership write on ordinary requests, so materialize its
    # deterministic identity only when an audited access is actually recorded.
    if principal.auth_mode == "local":
        _identity(session, principal.subject, principal.email)
    session.add(
        SensitiveAccessEvent(
            project_id=project_id,
            user_id=principal.user_id,
            action=action,
            resource_kind=resource_kind,
            resource_id=resource_id,
            outcome=outcome,
        )
    )
    session.commit()


def authorize_sensitive_read(
    session: Session,
    project_id: UUID,
    principal: Principal,
    *,
    action: str,
    resource_kind: str,
    resource_id: UUID | None,
):
    role = project_role(session, project_id, principal)
    outcome = "granted" if role in {"owner", "admin"} else "denied"
    audit_sensitive_access(
        session,
        project_id=project_id,
        principal=principal,
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        outcome=outcome,
    )
    if outcome == "denied":
        raise HTTPException(
            403, "Sensitive source content requires owner or admin access."
        )
