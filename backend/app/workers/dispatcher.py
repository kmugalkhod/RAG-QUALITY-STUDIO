"""Durable PostgreSQL queue relay and bounded recovery. Run one service."""

import logging
import time
from datetime import timedelta

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


def main():
    while True:
        try:
            dispatch_once()
            dispatch_indexes_once()
            dispatch_ingestion_once()
            dispatch_previews_once()
            from app.workers.experiments import dispatch_experiments_once

            dispatch_experiments_once()
        except Exception:
            logging.warning("Queue dispatch unavailable; retrying in five seconds.")
        time.sleep(5)


if __name__ == "__main__":
    main()
