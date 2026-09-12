"""Durable source-preview submission, reads, cancellation and retention."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.preview import SourcePreview, SourcePreviewItem
from app.schemas.ingestion import IngestionExecution
from app.services import pipelines
from app.services.documents import project


TERMINAL = ("succeeded", "failed", "cancelled")
RETAIN_TERMINAL_PER_PROJECT = 50


def _read(preview: SourcePreview):
    return {
        column.name: getattr(preview, column.name)
        for column in SourcePreview.__table__.columns
        if column.name not in ("execution", "execution_token", "dispatched_at")
    }


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
    preview = SourcePreview(
        project_id=project_id,
        execution=execution.model_dump(mode="json"),
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
