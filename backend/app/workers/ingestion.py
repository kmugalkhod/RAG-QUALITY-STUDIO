"""Bounded coordinator for fenced Existing Files ingestion stages."""

from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.document import ProcessingRun
from app.models.index import IndexVersion
from app.models.ingestion import IngestionRun, IngestionRunItem
from app.services import indexes
from app.workers.celery_app import celery
from app.workers.processing import now


def _fail(session: Session, job: IngestionRun, message: str):
    job.status = "failed"
    job.execution_token = None
    job.error = message
    job.updated_at = job.finished_at = now()


def _cancel_unpublished_work(session: Session, run_id: UUID):
    created = select(IngestionRunItem.processing_run_id).where(
        IngestionRunItem.run_id == run_id,
        IngestionRunItem.processing_created.is_(True),
    )
    session.execute(
        update(ProcessingRun)
        .where(
            ProcessingRun.id.in_(created),
            ProcessingRun.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Stopped because the parent ingestion run failed.",
            updated_at=now(),
            finished_at=now(),
        )
    )
    session.execute(
        update(IndexVersion)
        .where(
            IndexVersion.ingestion_run_id == run_id,
            IndexVersion.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Stopped because the parent ingestion run failed.",
            updated_at=now(),
            finished_at=now(),
        )
    )


def process_ingestion(run_id: UUID, db_engine=engine):
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid4()
    with Session(db_engine) as session:
        job = session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
        )
        if job is None or job.status != "queued" or job.failures >= 3:
            return
        job.status = "running"
        job.attempts += 1
        job.execution_token = token
        job.started_at = job.started_at or now()
        job.updated_at = now()
        job.error = None
        session.commit()
    try:
        with Session(db_engine) as session:
            job = session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return
            items = session.scalars(
                select(IngestionRunItem)
                .where(IngestionRunItem.run_id == run_id)
                .order_by(IngestionRunItem.document_id)
            ).all()
            failed = []
            waiting = []
            for item in items:
                processing = session.get(ProcessingRun, item.processing_run_id)
                if processing.status == "succeeded":
                    item.status = "ready"
                    item.chunk_count = processing.chunk_count
                    item.error = None
                elif processing.status in ("failed", "cancelled"):
                    item.status = "failed"
                    item.error = (
                        processing.error or "Document processing did not complete."
                    )
                    failed.append(item)
                else:
                    item.status = "processing"
                    waiting.append(item)
                item.updated_at = now()
            job.processed_count = sum(item.status == "ready" for item in items)
            job.failed_count = len(failed)
            job.chunk_count = sum(
                item.chunk_count for item in items if item.status == "ready"
            )
            if failed:
                _fail(
                    session,
                    job,
                    "One or more selected files could not be processed. Inspect run items and retry with a new run.",
                )
                _cancel_unpublished_work(session, run_id)
                session.commit()
                return
            if waiting:
                job.stage = "processing"
                job.progress = int(40 * job.processed_count / job.discovered_count)
                job.status = "queued"
                job.execution_token = None
                job.failures = 0
                job.dispatched_at = None
                job.updated_at = now()
                session.commit()
                return

            index = session.scalar(
                select(IndexVersion).where(IndexVersion.ingestion_run_id == run_id)
            )
            if index is None:
                indexes.create_index_from_processing_runs(
                    session,
                    job.project_id,
                    job.knowledge_set_id,
                    [item.processing_run_id for item in items],
                    ingestion_run_id=job.id,
                    commit=False,
                )
                job.stage = "indexing"
                job.progress = 40
                job.status = "queued"
                job.execution_token = None
                job.failures = 0
                job.dispatched_at = None
                job.updated_at = now()
                session.commit()
                return
            job.stage = "indexing"
            job.chunk_count = index.chunk_count
            job.embedded_count = index.embedded_count
            if index.status in ("queued", "running"):
                job.progress = 40 + int(59 * index.embedded_count / index.chunk_count)
                job.status = "queued"
                job.execution_token = None
                job.failures = 0
                job.dispatched_at = None
                job.updated_at = now()
                session.commit()
                return
            if index.status != "succeeded":
                _fail(
                    session,
                    job,
                    index.error or "The immutable index could not be published.",
                )
                session.commit()
                return
            for item in items:
                item.status = "succeeded"
                item.updated_at = now()
            job.status = "succeeded"
            job.stage = "complete"
            job.progress = 100
            job.processed_count = job.discovered_count
            job.failed_count = 0
            job.chunk_count = index.chunk_count
            job.embedded_count = index.embedded_count
            job.published_count = 1
            job.execution_token = None
            job.failures = 0
            job.error = None
            job.updated_at = job.finished_at = now()
            session.commit()
    except Exception as exc:
        transient = isinstance(exc, SQLAlchemyError)
        message = (
            exc.detail
            if isinstance(exc, HTTPException) and isinstance(exc.detail, str)
            else "Ingestion coordination was interrupted. The run will retry from its saved checkpoint."
        )
        with Session(db_engine) as session:
            job = session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            if job is None or job.status != "running" or job.execution_token != token:
                return
            job.failures += 1
            if transient and job.failures < 3:
                job.status = "queued"
                job.execution_token = None
                job.error = message
                job.updated_at = job.dispatched_at = now()
            else:
                _fail(session, job, message)
                _cancel_unpublished_work(session, run_id)
            session.commit()


@celery.task(name="ingestion.coordinate")
def coordinate_ingestion(run_id: str):
    process_ingestion(UUID(run_id))
