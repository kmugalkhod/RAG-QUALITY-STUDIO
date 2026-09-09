from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import engine
from app.models.document import Chunk, Document, ProcessingRun
from app.pipelines.parsing import MAX_CHUNKS, ProcessingError, pages, windows
from app.workers.celery_app import celery


def now():
    return datetime.now(timezone.utc)


def process(run_id: UUID, db_engine=engine):
    token = uuid4()
    # Workers use fresh sessions and READ COMMITTED row locks, not API snapshots.
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        job = session.scalar(
            select(ProcessingRun).where(ProcessingRun.id == run_id).with_for_update()
        )
        if job is None or job.status != "queued" or job.attempts >= 3:
            return
        job.status = "running"
        job.attempts += 1
        job.execution_token = token
        job.started_at = job.updated_at = now()
        job.error = None
        job.progress = 0
        doc = session.get(Document, job.document_id)
        path, media = settings.storage_path / doc.storage_name, doc.media_type
        size, overlap = job.chunk_size, job.overlap
        session.commit()
    try:
        chunks = []
        chunk_characters = 0
        for page, value, completed, total in pages(path, media):
            # Cancellation/recovery is observed between pages and bounded windows.
            for start, end, content in windows(value, size, overlap):
                if len(chunks) >= MAX_CHUNKS:
                    raise ProcessingError(
                        "Processing exceeds the 50,000 chunk limit. Increase chunk size or reduce overlap."
                    )
                chunk_characters += len(content)
                if chunk_characters > 10_000_000:
                    raise ProcessingError(
                        "Chunk text exceeds the 10,000,000 character output limit. Reduce overlap."
                    )
                chunks.append(
                    dict(
                        run_id=run_id,
                        ordinal=len(chunks),
                        page_number=page,
                        start_char=start,
                        end_char=end,
                        text=content,
                    )
                )
            with Session(db_engine) as session:
                changed = session.execute(
                    update(ProcessingRun)
                    .where(
                        ProcessingRun.id == run_id,
                        ProcessingRun.status == "running",
                        ProcessingRun.execution_token == token,
                    )
                    .values(
                        progress=min(95, int(95 * completed / total)), updated_at=now()
                    )
                )
                session.commit()
                if changed.rowcount != 1:
                    return
        with Session(
            db_engine.execution_options(isolation_level="READ COMMITTED")
        ) as session:
            job = session.scalar(
                select(ProcessingRun)
                .where(ProcessingRun.id == run_id)
                .with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return
            if not chunks:
                raise ProcessingError("The document contains no text.")
            for start in range(0, len(chunks), 500):
                session.execute(insert(Chunk), chunks[start : start + 500])
            job.status = "succeeded"
            job.chunk_count = len(chunks)
            job.progress = 100
            job.finished_at = job.updated_at = now()
            job.execution_token = None
            session.commit()
    except Exception as exc:
        # No raw source text, paths or driver errors are persisted or logged.
        transient = isinstance(exc, (OSError, SQLAlchemyError))
        message = (
            str(exc)
            if isinstance(exc, ProcessingError)
            else "Processing interrupted or unavailable. Retry processing."
        )
        with Session(
            db_engine.execution_options(isolation_level="READ COMMITTED")
        ) as session:
            job = session.scalar(
                select(ProcessingRun)
                .where(ProcessingRun.id == run_id)
                .with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return
            job.status = "queued" if transient and job.attempts < 3 else "failed"
            job.error = message
            job.execution_token = None
            job.updated_at = now()
            job.dispatched_at = now()  # dispatcher waits at least 30s before retry
            if job.status == "failed":
                job.finished_at = now()
            session.commit()


@celery.task(name="documents.process")
def process_document(run_id: str):
    process(UUID(run_id))
