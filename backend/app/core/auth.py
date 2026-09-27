"""Local-owner and OIDC authentication with project-role authorization."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_address
import logging
from typing import Annotated
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import jwt
import httpx
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.models.security import ProjectMembership, SensitiveAccessEvent, UserIdentity
from app.models.project import Project


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    subject: str
    email: str | None
    auth_mode: str
    organization_id: str | None = None
    organization_role: str | None = None


def validate_security_configuration() -> None:
    if settings.auth_mode == "clerk":
        issuer = settings.clerk_issuer.rstrip("/")
        if (
            not issuer.startswith("https://")
            or settings.clerk_jwks_url != f"{issuer}/.well-known/jwks.json"
            or not settings.clerk_secret_key.get_secret_value()
            or not settings.clerk_authorized_origins
            or any(
                not origin.startswith("http")
                for origin in settings.clerk_authorized_origins
            )
        ):
            raise RuntimeError("Clerk authentication is not configured.")
        return
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


def _clerk_claims(request: Request) -> dict:
    authorization = request.headers.get("authorization") or ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 16_384:
        raise HTTPException(401, "Authentication is required.")
    try:
        signing_key = _jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(
            token
        )
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer.rstrip("/"),
            options={
                "verify_aud": False,
                "require": ["exp", "iat", "nbf", "iss", "sub", "sid"],
            },
        )
    except jwt.PyJWTError as error:
        logger.warning("Clerk session token rejected: %s", type(error).__name__)
        raise HTTPException(401, "The authentication token is invalid.") from None
    if "azp" in claims and claims["azp"] not in settings.clerk_authorized_origins:
        party = claims["azp"]
        origin = urlsplit(party) if isinstance(party, str) else None
        logger.warning(
            "Clerk session token rejected: unauthorized party (%s://%s)",
            origin.scheme if origin else "invalid",
            origin.hostname if origin else "invalid",
        )
        raise HTTPException(401, "The authentication token is invalid.")
    if (
        claims.get("sts") == "pending"
        or not isinstance(claims.get("sub"), str)
        or not claims["sub"].startswith("user_")
        or not isinstance(claims.get("sid"), str)
        or not claims["sid"].startswith("sess_")
    ):
        logger.warning("Clerk session token rejected: claim validation")
        raise HTTPException(401, "The authentication token is invalid.")
    organization = claims.get("o")
    organization_id = (
        organization.get("id")
        if isinstance(organization, dict)
        else claims.get("org_id")
    )
    if not isinstance(organization_id, str) or not organization_id.startswith("org_"):
        raise HTTPException(403, "Select an organization to continue.")
    claims["_organization_id"] = organization_id
    return claims


def _clerk_membership(subject: str, organization_id: str) -> str | None:
    """Check live membership so removed users cannot ride a still-valid JWT."""
    try:
        with httpx.Client(timeout=5.0) as client:
            for offset in range(0, 500, 100):
                response = client.get(
                    f"https://api.clerk.com/v1/users/{subject}/organization_memberships",
                    params={"limit": 100, "offset": offset},
                    headers={
                        "Authorization": f"Bearer {settings.clerk_secret_key.get_secret_value()}"
                    },
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("data"), list
                ):
                    raise ValueError("Invalid membership response")
                for membership in payload["data"]:
                    if membership.get("organization", {}).get("id") == organization_id:
                        return membership.get("role")
                if offset + len(payload["data"]) >= payload.get("total_count", 0):
                    return None
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(
            503, "Organization membership could not be verified."
        ) from None
    raise HTTPException(503, "Organization membership could not be verified.")


def _identity(session: Session, subject: str, email: str | None) -> UserIdentity:
    if not subject or len(subject) > 500:
        raise HTTPException(401, "The authentication token is invalid.")
    if email is not None and len(email) > 320:
        email = None
    existing = session.scalar(
        select(UserIdentity).where(UserIdentity.external_subject == subject)
    )
    if existing is not None and existing.email == email:
        return existing
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
    elif settings.auth_mode == "clerk":
        # The development configuration has local raw-artifact storage; keep it
        # restricted to loopback until a shared KMS/Vault deployment is configured.
        if not _loopback_request(request):
            raise HTTPException(
                403, "Clerk development access is restricted to loopback."
            )
        claims = _clerk_claims(request)
        subject = claims["sub"]
        organization_id = claims["_organization_id"]
        organization_role = _clerk_membership(subject, organization_id)
        if not organization_role:
            raise HTTPException(403, "Organization membership is required.")
        email = None
    else:
        claims = _oidc_claims(request)
        subject = claims.get("sub")
        email = claims.get("email")
        if not isinstance(subject, str) or (
            email is not None and not isinstance(email, str)
        ):
            raise HTTPException(401, "The authentication token is invalid.")
    for attempt in range(3):
        try:
            identity = _identity(session, subject, email)
            session.commit()
            break
        except OperationalError as error:
            session.rollback()
            if getattr(error.orig, "sqlstate", None) != "40001" or attempt == 2:
                raise
    return Principal(
        identity.id,
        subject,
        email,
        settings.auth_mode,
        organization_id if settings.auth_mode == "clerk" else None,
        organization_role if settings.auth_mode == "clerk" else None,
    )


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
    statement = (
        select(ProjectMembership.role)
        .join(Project, Project.id == ProjectMembership.project_id)
        .where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == principal.user_id,
        )
    )
    if principal.auth_mode == "clerk":
        statement = statement.where(
            Project.organization_id == principal.organization_id
        )
    return session.scalar(statement)


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
        if session.get(UserIdentity, principal.user_id) is None:
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
