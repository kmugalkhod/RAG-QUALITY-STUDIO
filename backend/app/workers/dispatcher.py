"""Durable PostgreSQL queue relay and bounded recovery. Run one service."""

import logging
import time
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.document import ProcessingRun
from app.workers.processing import now, process_document


def dispatch_once(db_engine=engine, send=None):
    send = send or (lambda run_id: process_document.apply_async(args=[str(run_id)]))
    current = now()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        stale = session.scalars(
            select(ProcessingRun)
            .where(
                ProcessingRun.status == "running",
                ProcessingRun.started_at < current - timedelta(seconds=180),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in stale:
            job.execution_token = None
            job.status = "failed" if job.attempts >= 3 else "queued"
            job.error = (
                "Worker interrupted or exceeded processing time limit."
                if job.status == "failed"
                else "Recovering an interrupted worker attempt."
            )
            job.updated_at = current
            job.dispatched_at = None
            if job.status == "failed":
                job.finished_at = current
        session.commit()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        queued = session.scalars(
            select(ProcessingRun)
            .where(
                ProcessingRun.status == "queued",
                or_(
                    ProcessingRun.dispatched_at.is_(None),
                    ProcessingRun.dispatched_at < current - timedelta(seconds=30),
                ),
            )
            .order_by(ProcessingRun.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for job in queued:
            send(job.id)
            job.dispatched_at = current
        session.commit()


def dispatch_indexes_once(db_engine=engine, send=None):
    from app.models.index import IndexVersion
    from app.workers.indexing import index_documents

    send = send or (lambda index_id: index_documents.apply_async(args=[str(index_id)]))
    current = now()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        stale = session.scalars(
            select(IndexVersion)
            .where(
                IndexVersion.status == "running",
                IndexVersion.started_at < current - timedelta(seconds=180),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in stale:
            job.failures += 1
            job.execution_token = None
            job.status = "failed" if job.failures >= 3 else "queued"
            job.error = "Indexing worker interrupted or exceeded its time limit."
            job.updated_at = current
            job.dispatched_at = None
            if job.status == "failed":
                job.finished_at = current
        session.commit()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        queued = session.scalars(
            select(IndexVersion)
            .where(
                IndexVersion.status == "queued",
                or_(
                    IndexVersion.dispatched_at.is_(None),
                    IndexVersion.dispatched_at < current - timedelta(seconds=30),
                ),
            )
            .order_by(IndexVersion.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for job in queued:
            send(job.id)
            job.dispatched_at = current
        session.commit()


def dispatch_ingestion_once(db_engine=engine, send=None):
    from app.models.ingestion import IngestionRun, IngestionRunItem
    from app.models.index import IndexVersion
    from app.workers.ingestion import coordinate_ingestion

    send = send or (lambda run_id: coordinate_ingestion.apply_async(args=[str(run_id)]))
    current = now()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        stale = session.scalars(
            select(IngestionRun)
            .where(
                IngestionRun.status == "running",
                IngestionRun.started_at < current - timedelta(seconds=180),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in stale:
            if job.snapshot.get(
                "source_kind"
            ) == "website" and job.started_at >= current - timedelta(seconds=3660):
                continue
            job.failures += 1
            job.execution_token = None
            job.status = "failed" if job.failures >= 3 else "queued"
            job.error = (
                "Ingestion worker was interrupted; recovery uses its saved checkpoint."
            )
            job.updated_at = current
            job.dispatched_at = None
            if job.status == "failed":
                job.finished_at = current
                created_processing = select(IngestionRunItem.processing_run_id).where(
                    IngestionRunItem.run_id == job.id,
                    IngestionRunItem.processing_created.is_(True),
                )
                session.execute(
                    update(ProcessingRun)
                    .where(
                        ProcessingRun.id.in_(created_processing),
                        ProcessingRun.status.in_(["queued", "running"]),
                    )
                    .values(
                        status="cancelled",
                        execution_token=None,
                        error="Parent ingestion recovery exhausted its retry budget.",
                        updated_at=current,
                        finished_at=current,
                    )
                )
                session.execute(
                    update(IndexVersion)
                    .where(
                        IndexVersion.ingestion_run_id == job.id,
                        IndexVersion.status.in_(["queued", "running"]),
                    )
                    .values(
                        status="cancelled",
                        execution_token=None,
                        error="Parent ingestion recovery exhausted its retry budget.",
                        updated_at=current,
                        finished_at=current,
                    )
                )
        session.commit()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        queued = session.scalars(
            select(IngestionRun)
            .where(
                IngestionRun.status == "queued",
                or_(
                    IngestionRun.dispatched_at.is_(None),
                    IngestionRun.dispatched_at < current - timedelta(seconds=30),
                ),
            )
            .order_by(IngestionRun.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for job in queued:
            send(job.id)
            job.dispatched_at = current
        session.commit()


def dispatch_previews_once(db_engine=engine, send=None):
    from app.models.preview import SourcePreview
    from app.workers.previews import preview_sources

    send = send or (
        lambda preview_id: preview_sources.apply_async(args=[str(preview_id)])
    )
    current = now()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        stale = session.scalars(
            select(SourcePreview)
            .where(
                SourcePreview.status == "running",
                SourcePreview.started_at < current - timedelta(seconds=3660),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for preview in stale:
            preview.failures += 1
            preview.execution_token = None
            preview.status = "failed" if preview.failures >= 3 else "queued"
            preview.error = "Source preview worker exceeded its bounded deadline."
            preview.updated_at = current
            preview.dispatched_at = None
            if preview.status == "failed":
                preview.finished_at = current
        session.commit()
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        queued = session.scalars(
            select(SourcePreview)
            .where(
                SourcePreview.status == "queued",
                or_(
                    SourcePreview.dispatched_at.is_(None),
                    SourcePreview.dispatched_at < current - timedelta(seconds=30),
                ),
            )
            .order_by(SourcePreview.created_at)
            .limit(10)
            .with_for_update(skip_locked=True)
        ).all()
        for preview in queued:
            send(preview.id)
            preview.dispatched_at = current
        session.commit()


def dispatch_schedules_once(db_engine=engine, current=None):
    """Claim due schedules durably and coalesce each to one new run."""
    from app.models.ingestion import IngestionRun, IngestionSchedule
    from app.models.pipeline import PipelineVersion
    from app.schemas.schedule import Cadence
    from pydantic import TypeAdapter
    from app.services import ingestion, schedules

    current = current or now()
    claimed = []
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        tracked = session.scalars(
            select(IngestionSchedule)
            .where(
                IngestionSchedule.last_run_id.is_not(None),
                IngestionSchedule.last_outcome.in_(["queued", "running"]),
            )
            .order_by(IngestionSchedule.updated_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for row in tracked:
            schedules.refresh_outcome(session, row)
        stale = session.scalars(
            select(IngestionSchedule)
            .where(
                IngestionSchedule.claim_token.is_not(None),
                IngestionSchedule.claimed_at < current - timedelta(seconds=60),
            )
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for row in stale:
            row.claim_token = row.claimed_at = None
        session.flush()
        due = session.scalars(
            select(IngestionSchedule)
            .where(
                IngestionSchedule.status == "enabled",
                IngestionSchedule.next_run_at <= current,
                IngestionSchedule.claim_token.is_(None),
            )
            .order_by(IngestionSchedule.next_run_at, IngestionSchedule.id)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for row in due:
            row.claim_token = uuid4()
            row.claimed_at = current
            row.updated_at = current
            claimed.append((row.id, row.claim_token))
        session.commit()

    for schedule_id, token in claimed:
        with Session(
            db_engine.execution_options(isolation_level="READ COMMITTED")
        ) as session:
            row = session.scalar(
                select(IngestionSchedule)
                .where(IngestionSchedule.id == schedule_id)
                .with_for_update()
            )
            if row is None or row.status != "enabled" or row.claim_token != token:
                continue
            due_at = row.next_run_at
            try:
                version = session.get(PipelineVersion, row.pipeline_version_id)
                recovered = session.scalar(
                    select(IngestionRun)
                    .where(
                        IngestionRun.schedule_id == row.id,
                        IngestionRun.created_at >= row.next_run_at,
                    )
                    .order_by(IngestionRun.created_at.desc())
                    .limit(1)
                )
                result = None
                if recovered is None:
                    result = ingestion.start_run(
                        session,
                        row.project_id,
                        version.pipeline_id,
                        version.id,
                        trigger_kind="scheduled",
                        schedule_id=row.id,
                    )
                run_id = recovered.id if recovered is not None else result["id"]
                run_outcome = recovered.status if recovered is not None else "queued"
            except Exception as exc:
                session.rollback()
                recovered = session.scalar(
                    select(IngestionRun)
                    .where(
                        IngestionRun.schedule_id == schedule_id,
                        IngestionRun.created_at >= due_at,
                    )
                    .order_by(IngestionRun.created_at.desc())
                    .limit(1)
                )
                if recovered is not None:
                    run_id = recovered.id
                    run_outcome = recovered.status
                else:
                    row = session.scalar(
                        select(IngestionSchedule)
                        .where(IngestionSchedule.id == schedule_id)
                        .with_for_update()
                    )
                    if row is None or row.claim_token != token:
                        continue
                    is_overlap = (
                        isinstance(exc, HTTPException)
                        and exc.status_code == 409
                        and exc.detail
                        == "This knowledge set already has an active ingestion run."
                    )
                    row.last_outcome = "skipped" if is_overlap else "failed"
                    row.last_error = (
                        "A destination run is already active."
                        if is_overlap
                        else "The scheduled run could not be created safely."
                    )
                    cadence = TypeAdapter(Cadence).validate_python(row.cadence)
                    row.next_run_at = schedules.next_due(cadence, current)
                    row.claim_token = row.claimed_at = None
                    row.updated_at = current
                    session.commit()
                    if not isinstance(exc, HTTPException):
                        logging.warning(
                            "Scheduled ingestion creation failed for schedule %s.",
                            schedule_id,
                        )
                    continue

            row = session.scalar(
                select(IngestionSchedule)
                .where(IngestionSchedule.id == schedule_id)
                .with_for_update()
            )
            if row is None:
                continue
            if row.claim_token != token:
                if row.claim_token is None:
                    row.last_run_id = run_id
                    row.last_triggered_at = current
                    row.last_outcome = run_outcome
                    row.last_error = None
                    row.updated_at = current
                    session.commit()
                continue
            if row.status != "enabled":
                row.claim_token = row.claimed_at = None
                row.updated_at = current
                session.commit()
                continue
            cadence = TypeAdapter(Cadence).validate_python(row.cadence)
            row.last_run_id = run_id
            row.last_triggered_at = current
            row.last_outcome = run_outcome
            row.last_error = None
            row.next_run_at = schedules.next_due(cadence, current)
            row.claim_token = row.claimed_at = None
            row.updated_at = current
            session.commit()


def main():
    while True:
        try:
            dispatch_once()
            dispatch_indexes_once()
            dispatch_schedules_once()
            dispatch_ingestion_once()
            dispatch_previews_once()
            from app.services.artifact_storage import cleanup_expired_raw_artifacts

            cleanup_expired_raw_artifacts(engine)
            from app.workers.experiments import dispatch_experiments_once

            dispatch_experiments_once()
        except Exception:
            logging.warning("Queue dispatch unavailable; retrying in five seconds.")
        time.sleep(5)


if __name__ == "__main__":
    main()
