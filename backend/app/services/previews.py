"""Durable source-preview submission, reads, cancellation and retention."""

import hashlib
import json
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.preview import (
    SourcePreview,
    SourcePreviewItem,
    SourcePreviewRepresentation,
)
from app.schemas.ingestion import IngestionExecution
from app.services import pipelines
from app.services.documents import project
from app.workers.processing import now


TERMINAL = ("succeeded", "failed", "cancelled", "expired")
RETAIN_TERMINAL_PER_PROJECT = 50
PREVIEW_TTL = timedelta(hours=24)


def _configuration_hash(execution: IngestionExecution) -> str:
    encoded = json.dumps(
        execution.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _expired(preview: SourcePreview) -> bool:
    return preview.status in TERMINAL and preview.expires_at <= now()


def _read(preview: SourcePreview):
    value = {
        column.name: getattr(preview, column.name)
        for column in SourcePreview.__table__.columns
        if column.name not in ("execution", "execution_token", "dispatched_at")
    }
    if _expired(preview):
        value["status"] = "expired"
    return value


def start(session: Session, project_id: UUID, execution: IngestionExecution):
    project(session, project_id)
    pipelines.validate_ingestion(session, project_id, execution)
    if session.scalar(
        select(SourcePreview.id).where(
            SourcePreview.project_id == project_id,
            SourcePreview.status.in_(["queued", "running"]),
        )
    ):
        raise HTTPException(409, "This project already has an active source preview.")
    retained = session.scalars(
        select(SourcePreview.id)
        .where(
            SourcePreview.project_id == project_id,
            SourcePreview.status.in_(TERMINAL),
        )
        .order_by(SourcePreview.created_at.desc(), SourcePreview.id.desc())
        .offset(RETAIN_TERMINAL_PER_PROJECT - 1)
    ).all()
    if retained:
        session.execute(delete(SourcePreview).where(SourcePreview.id.in_(retained)))
    source_kinds = {
        node.config.kind for node in execution.nodes if node.type == "source"
    }
    fetch_mode = (
        "cached-artifact" if source_kinds == {"existing_files"} else "network"
    )
    preview = SourcePreview(
        project_id=project_id,
        execution=execution.model_dump(mode="json"),
        configuration_hash=_configuration_hash(execution),
        fetch_mode=fetch_mode,
        expires_at=now() + PREVIEW_TTL,
        cost_basis={
            "currency": "USD",
            "known_monetary_cost": None,
            "local_compute_measurement": "duration_ms",
            "excluded_work": ["embedding", "generation", "publication"],
        },
    )
    session.add(preview)
    session.commit()
    session.refresh(preview)
    return _read(preview)


def get(session: Session, project_id: UUID, preview_id: UUID):
    preview = session.scalar(
        select(SourcePreview).where(
            SourcePreview.id == preview_id,
            SourcePreview.project_id == project_id,
        )
    )
    if preview is None:
        raise HTTPException(404, "Source preview not found in this project.")
    return preview


def read(session: Session, project_id: UUID, preview_id: UUID):
    return _read(get(session, project_id, preview_id))


def items(
    session: Session, project_id: UUID, preview_id: UUID, limit: int, offset: int
):
    preview = get(session, project_id, preview_id)
    if _expired(preview):
        raise HTTPException(410, "This processing preview expired. Retry it.")
    total = session.scalar(
        select(func.count())
        .select_from(SourcePreviewItem)
        .where(SourcePreviewItem.preview_id == preview.id)
    )
    rows = session.scalars(
        select(SourcePreviewItem)
        .where(SourcePreviewItem.preview_id == preview.id)
        .order_by(SourcePreviewItem.ordinal)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                column.name: getattr(item, column.name)
                for column in SourcePreviewItem.__table__.columns
                if column.name not in ("preview_id", "created_at")
            }
            for item in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def representations(
    session: Session,
    project_id: UUID,
    preview_id: UUID,
    item_ordinal: int,
    stage: str,
    limit: int,
    offset: int,
):
    preview = get(session, project_id, preview_id)
    if _expired(preview):
        raise HTTPException(410, "This processing preview expired. Retry it.")
    if session.get(SourcePreviewItem, (preview.id, item_ordinal)) is None:
        raise HTTPException(404, "Preview item not found in this project.")
    condition = (
        (SourcePreviewRepresentation.preview_id == preview.id)
        & (SourcePreviewRepresentation.item_ordinal == item_ordinal)
        & (SourcePreviewRepresentation.stage == stage)
    )
    total = session.scalar(
        select(func.count())
        .select_from(SourcePreviewRepresentation)
        .where(condition)
    )
    rows = session.scalars(
        select(SourcePreviewRepresentation)
        .where(condition)
        .order_by(SourcePreviewRepresentation.ordinal)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                "stage": row.stage,
                "ordinal": row.ordinal,
                "block_type": row.block_type,
                "text": row.text,
                "metadata": row.metadata_json,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def cancel(session: Session, project_id: UUID, preview_id: UUID):
    preview = get(session, project_id, preview_id)
    if preview.status not in ("queued", "running"):
        return _read(preview)
    session.execute(
        update(SourcePreview)
        .where(
            SourcePreview.id == preview.id,
            SourcePreview.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Cancelled. An in-flight request may finish, but its result cannot be saved.",
            updated_at=func.now(),
            finished_at=func.now(),
        )
    )
    session.commit()
    session.refresh(preview)
    return _read(preview)


def retry(session: Session, project_id: UUID, preview_id: UUID):
    previous = get(session, project_id, preview_id)
    if previous.status in ("queued", "running"):
        raise HTTPException(409, "This processing preview is still active.")
    execution = IngestionExecution.model_validate(previous.execution)
    return start(session, project_id, execution)
