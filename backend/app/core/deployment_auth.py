"""Deployment bearer keys are independent from Clerk workspace sessions."""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.deployment import AnswerDeploymentKey
from app.services.deployments import _event
from app.services.deployment_commands import record

TOKEN = re.compile(r"^(rqs_live_[0-9a-f]{16})_([A-Za-z0-9_-]{43})$")


def _pepper(version):
    secret = settings.deployment_key_peppers.get(version)
    if secret is None or len(secret.get_secret_value().encode()) < 32:
        raise HTTPException(503, "Deployment key verification is unavailable.")
    return secret.get_secret_value().encode()


def _hash(secret, version):
    return hmac.new(_pepper(version), secret.encode(), hashlib.sha256).hexdigest()


def _enabled():
    if not settings.deployed_answers_enabled:
        raise HTTPException(503, "Deployed answers are disabled.")
    if settings.auth_mode == "local" and not settings.deployment_local_keys_enabled:
        raise HTTPException(503, "Local deployment keys are disabled.")


def create_key(
    session,
    deployment,
    label,
    expires_at,
    actor,
    *,
    client_id=None,
    rotated_from=None,
    command=None,
):
    _enabled()
    version = settings.deployment_active_pepper
    _pepper(version)
    now = datetime.now(timezone.utc)
    if deployment.state == "archived":
        raise HTTPException(409, "Archived deployments cannot issue keys.")
    if expires_at is not None and (
        expires_at <= now or expires_at > now + timedelta(days=365)
    ):
        raise HTTPException(422, "Expiry must be within the next 365 days.")
    prefix = "rqs_live_" + secrets.token_hex(8)
    secret = prefix + "_" + secrets.token_urlsafe(32)
    row = AnswerDeploymentKey(
        deployment_id=deployment.id,
        organization_id=deployment.organization_id,
        project_id=deployment.project_id,
        client_id=client_id or uuid4(),
        prefix=prefix,
        secret_hash=_hash(secret, version),
        pepper_version=version,
        label=label,
        created_by=actor,
        expires_at=expires_at,
        rotation_of_key_id=rotated_from,
    )
    session.add(row)
    session.flush()
    _event(
        session,
        deployment,
        "key_rotated" if rotated_from else "key_created",
        actor,
        reason=label,
    )
    record(session, command, row.id, metadata(row), secret_issued=True)
    session.commit()
    return row, secret


def metadata(row):
    return {
        "id": row.id,
        "prefix": row.prefix,
        "client_id": row.client_id,
        "label": row.label,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "last_used_at": row.last_used_at,
        "rotation_of_key_id": row.rotation_of_key_id,
    }


def verify_key(session, deployment, authorization):
    _enabled()
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or len(authorization) > 180
    ):
        raise HTTPException(401, "A deployment bearer key is required.")
    secret = authorization[7:]
    match = TOKEN.fullmatch(secret)
    if not match:
        raise HTTPException(401, "Invalid deployment key.")
    row = session.scalar(
        select(AnswerDeploymentKey).where(
            AnswerDeploymentKey.prefix == match.group(1),
            AnswerDeploymentKey.deployment_id == deployment.id,
        )
    )
    digest = _hash(
        secret, row.pepper_version if row else settings.deployment_active_pepper
    )
    if not hmac.compare_digest(digest, row.secret_hash if row else "0" * 64):
        raise HTTPException(401, "Invalid deployment key.")
    if deployment.state == "archived":
        raise HTTPException(410, "Deployment archived.")
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None or (
        row.expires_at is not None and row.expires_at <= now
    ):
        raise HTTPException(401, "Invalid deployment key.")
    if row.last_used_at is None or row.last_used_at < now - timedelta(hours=1):
        row.last_used_at = now
        session.flush()
    return row


def rotate_key(session, deployment, row, actor, *, command=None):
    if row.deployment_id != deployment.id or row.revoked_at is not None:
        raise HTTPException(404, "Deployment key not found.")
    now = datetime.now(timezone.utc)
    if row.expires_at is not None and row.expires_at <= now:
        raise HTTPException(409, "Expired keys cannot be rotated.")
    grace = now + timedelta(minutes=settings.deployment_key_rotation_grace_minutes)
    row.expires_at = min(row.expires_at, grace) if row.expires_at else grace
    session.flush()
    return create_key(
        session,
        deployment,
        row.label,
        None,
        actor,
        client_id=row.client_id,
        rotated_from=row.id,
        command=command,
    )


def revoke_key(session, deployment, row, actor, *, command=None):
    if row.deployment_id != deployment.id:
        raise HTTPException(404, "Deployment key not found.")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        _event(session, deployment, "key_revoked", actor, reason=row.label)
    if command is not None:
        record(session, command, row.id, metadata(row))
    if row.revoked_at is not None:
        session.commit()
    return row
