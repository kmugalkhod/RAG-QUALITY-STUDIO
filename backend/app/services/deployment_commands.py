"""Transactional 24-hour management replay receipts."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text

from app.models.deployment import DeploymentCommandReceipt


def prepare(session, principal_id, project_id, deployment_id, kind, key, body):
    if key is None:
        return None, None
    if not (1 <= len(key) <= 128) or any(ord(ch) < 33 or ord(ch) > 126 for ch in key):
        raise HTTPException(422, "invalid_idempotency_key")
    body_hash = hashlib.sha256(
        json.dumps(
            jsonable_encoder(
                {
                    "project_id": project_id,
                    "deployment_id": deployment_id,
                    "body": body,
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    session.execute(text("SELECT pg_advisory_xact_lock(745199392)"))
    row = session.scalar(
        select(DeploymentCommandReceipt)
        .where(
            DeploymentCommandReceipt.principal_id == principal_id,
            DeploymentCommandReceipt.command_kind == kind,
            DeploymentCommandReceipt.key_hash == key_hash,
        )
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if row is not None and row.expires_at <= now:
        session.delete(row)
        session.flush()
        row = None
    if row is not None:
        if row.request_hash != body_hash:
            raise HTTPException(409, "idempotency_conflict")
        if row.secret_issued:
            raise HTTPException(
                409,
                {
                    "code": "key_secret_already_issued",
                    "message": "The key secret was already issued once. Rotate or create another key if it was lost.",
                    "details": [{"key_id": str(row.resource_id)}],
                },
            )
        return None, row
    return (
        principal_id,
        project_id,
        deployment_id,
        kind,
        key_hash,
        body_hash,
        now,
    ), None


def record(session, context, resource_id, response, *, secret_issued=False):
    if context is None:
        return
    principal_id, project_id, deployment_id, kind, key_hash, body_hash, now = context
    session.add(
        DeploymentCommandReceipt(
            principal_id=principal_id,
            project_id=project_id,
            deployment_id=deployment_id,
            command_kind=kind,
            key_hash=key_hash,
            request_hash=body_hash,
            resource_id=resource_id,
            response=jsonable_encoder(response),
            secret_issued=secret_issued,
            expires_at=now + timedelta(hours=24),
        )
    )
