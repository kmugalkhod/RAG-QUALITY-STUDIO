"""Opaque short-lived widget credentials. Customer authentication stays on their backend."""

import hashlib
import hmac
import ipaddress
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.core.config import settings
from app.models.deployment import AnswerDeploymentKey, WidgetToken

_TOKEN = re.compile(r"^rqs_widget_[A-Za-z0-9_-]{43}$")


def canonical_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise HTTPException(422, "origin_not_allowed") from None
    if (
        not host
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(422, "origin_not_allowed")
    loopback = False
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise HTTPException(422, "origin_not_allowed")
    normalized = f"{parsed.scheme}://{host.lower()}" + (f":{port}" if port else "")
    if value != normalized:
        raise HTTPException(422, "origin_not_allowed")
    return value


def _key() -> bytes:
    if not settings.widget_enabled:
        raise HTTPException(503, "widget_unavailable")
    value = settings.widget_token_hash_key.get_secret_value().encode()
    if len(value) < 32:
        raise HTTPException(503, "widget_unavailable")
    return value


def _hash(kind: str, value: str) -> str:
    return hmac.new(_key(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def ensure_public_key(session, deployment, actor):
    key = session.scalar(
        select(AnswerDeploymentKey).where(
            AnswerDeploymentKey.deployment_id == deployment.id,
            AnswerDeploymentKey.kind == "public_widget",
        )
    )
    if key is not None:
        return key
    key = AnswerDeploymentKey(
        deployment_id=deployment.id,
        organization_id=deployment.organization_id,
        project_id=deployment.project_id,
        client_id=uuid.uuid4(),
        prefix="rqs_internal_" + secrets.token_hex(8),
        secret_hash=secrets.token_hex(32),
        pepper_version="internal",
        label="Studio public widget",
        kind="public_widget",
        created_by=actor,
    )
    session.add(key)
    session.flush()
    return key


def issue_public(session, deployment, visitor: str, site_origin: str):
    if not deployment.widget_public_enabled:
        raise HTTPException(403, "public_widget_disabled")
    key = session.scalar(
        select(AnswerDeploymentKey).where(
            AnswerDeploymentKey.deployment_id == deployment.id,
            AnswerDeploymentKey.kind == "public_widget",
        )
    )
    if key is None:
        raise HTTPException(503, "widget_unavailable")
    return issue(session, deployment, key, visitor, site_origin)


def issue(session, deployment, key, visitor: str, site_origin: str):
    canonical_origin(site_origin)
    if deployment.state != "active" or not deployment.active_release_id:
        raise HTTPException(409, "deployment_not_active")
    if not deployment.widget_enabled:
        raise HTTPException(403, "widget_disabled")
    if site_origin not in deployment.widget_origins:
        raise HTTPException(403, "origin_not_allowed")
    session.execute(text("SELECT pg_advisory_xact_lock(745199391)"))
    now = datetime.now(timezone.utc)
    minute = now - timedelta(minutes=1)
    exchanges = session.scalar(
        select(func.count())
        .select_from(WidgetToken)
        .where(
            WidgetToken.deployment_id == deployment.id,
            WidgetToken.key_id == key.id,
            WidgetToken.created_at >= minute,
        )
    )
    if exchanges >= settings.widget_exchange_rpm:
        raise HTTPException(429, "rate_limited")
    binding = _hash("visitor", visitor)
    # Keep existing run idempotency unique across token renewals and key rotation.
    client_id = uuid.uuid5(uuid.UUID(str(deployment.id)), binding)
    secret = "rqs_widget_" + secrets.token_urlsafe(32)
    expiry = now + timedelta(minutes=5)
    row = WidgetToken(
        deployment_id=deployment.id,
        organization_id=deployment.organization_id,
        project_id=deployment.project_id,
        key_id=key.id,
        token_hash=_hash("token", secret),
        visitor_binding=binding,
        client_id=client_id,
        site_origin=site_origin,
        expires_at=expiry,
    )
    session.add(row)
    session.commit()
    return {"token": secret, "expires_at": expiry, "token_type": "Bearer"}


def verify(session, deployment, authorization: str | None, origin: str | None):
    if origin != settings.widget_frame_origin:
        raise HTTPException(403, "origin_not_allowed")
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or len(authorization) > 160
    ):
        raise HTTPException(401, "widget_token_required")
    secret = authorization[7:]
    if not _TOKEN.fullmatch(secret):
        raise HTTPException(401, "widget_token_required")
    digest = _hash("token", secret)
    token = session.scalar(
        select(WidgetToken).where(
            WidgetToken.token_hash == digest,
            WidgetToken.deployment_id == deployment.id,
        )
    )
    if token is None:
        raise HTTPException(401, "widget_token_required")
    if token.revoked_at is not None:
        raise HTTPException(401, "widget_token_revoked")
    now = datetime.now(timezone.utc)
    if token.expires_at <= now:
        raise HTTPException(401, "widget_token_expired")
    key = session.get(AnswerDeploymentKey, token.key_id)
    if (
        key is None
        or key.revoked_at is not None
        or (key.expires_at and key.expires_at <= now)
    ):
        raise HTTPException(401, "widget_token_revoked")
    if key.kind == "public_widget" and not deployment.widget_public_enabled:
        raise HTTPException(403, "public_widget_disabled")
    if deployment.state == "archived":
        raise HTTPException(410, "deployment_archived")
    if (
        not deployment.widget_enabled
        or token.site_origin not in deployment.widget_origins
    ):
        raise HTTPException(403, "widget_disabled")
    return token, key


def revoke_visitor(session, deployment, visitor: str, site_origin: str):
    canonical_origin(site_origin)
    if site_origin not in deployment.widget_origins:
        raise HTTPException(403, "origin_not_allowed")
    binding = _hash("visitor", visitor)
    now = datetime.now(timezone.utc)
    session.query(WidgetToken).filter(
        WidgetToken.deployment_id == deployment.id,
        WidgetToken.visitor_binding == binding,
        WidgetToken.site_origin == site_origin,
        WidgetToken.revoked_at.is_(None),
    ).update({WidgetToken.revoked_at: now})
    session.commit()
