"""One bounded embedding batch per Celery delivery; PostgreSQL owns checkpoints."""

from uuid import UUID, uuid4
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk, IndexVersion
from app.providers import embeddings
from app.workers.celery_app import celery
from app.workers.processing import now

BATCH_SIZE = 16
MAX_BATCH_CHARACTERS = 24000


def process_index(index_id: UUID, db_engine=engine):
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid4()
    with Session(db_engine) as session:
        job = session.scalar(
            select(IndexVersion).where(IndexVersion.id == index_id).with_for_update()
        )
        if job is None or job.status != "queued" or job.failures >= 3:
            return
        job.status = "running"
        job.attempts += 1
        job.execution_token = token
        job.started_at = job.updated_at = now()
        job.error = None
        config = embeddings.EmbeddingConfig.model_validate(job.embedding_config)
        project_id = job.project_id
        session.commit()
    try:
        provider = embeddings.provider_for(config)
        with Session(db_engine) as session:
            candidates = session.execute(
                select(IndexChunk.run_id, IndexChunk.ordinal, Chunk.text)
                .join(
                    Chunk,
                    (Chunk.run_id == IndexChunk.run_id)
                    & (Chunk.ordinal == IndexChunk.ordinal),
                )
                .where(IndexChunk.index_id == index_id, IndexChunk.embedding.is_(None))
                .order_by(IndexChunk.run_id, IndexChunk.ordinal)
                .limit(BATCH_SIZE)
            ).all()
            batch = []
            characters = 0
            for row in candidates:
                if batch and characters + len(row.text) > MAX_BATCH_CHARACTERS:
                    break
                batch.append(row)
                characters += len(row.text)
            vectors = {}
            # Exact text plus the complete embedding config, only within this project.
            old_chunk = aliased(Chunk)
            for run_id, ordinal, value in batch:
                cached = session.scalar(
                    select(IndexChunk.embedding)
                    .join(IndexVersion, IndexVersion.id == IndexChunk.index_id)
                    .join(
                        old_chunk,
                        (old_chunk.run_id == IndexChunk.run_id)
                        & (old_chunk.ordinal == IndexChunk.ordinal),
                    )
                    .join(ProcessingRun, ProcessingRun.id == old_chunk.run_id)
                    .join(Document, Document.id == ProcessingRun.document_id)
                    .where(
                        IndexVersion.project_id == project_id,
                        Document.project_id == project_id,
                        IndexVersion.embedding_config == config.model_dump(),
                        IndexChunk.embedding.is_not(None),
                        old_chunk.text == value,
                    )
                    .limit(1)
                )
                if cached is not None:
                    vectors[(run_id, ordinal)] = embeddings.validate_vectors(
                        [cached.tolist()], 1, config.dimensions
                    )[0]
        missing = [row for row in batch if (row.run_id, row.ordinal) not in vectors]
        if missing:
            with Session(db_engine) as session:
                if not session.scalar(
                    select(IndexVersion.id).where(
                        IndexVersion.id == index_id,
                        IndexVersion.status == "running",
                        IndexVersion.execution_token == token,
                    )
                ):
                    return
            values = embeddings.validate_vectors(
                provider.embed([r.text for r in missing]),
                len(missing),
                config.dimensions,
            )
            vectors.update(
                {
                    (row.run_id, row.ordinal): value
                    for row, value in zip(missing, values, strict=True)
                }
            )
        with Session(db_engine) as session:
            job = session.scalar(
                select(IndexVersion)
                .where(IndexVersion.id == index_id)
                .with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return
            for (run_id, ordinal), vector in vectors.items():
                member = session.get(IndexChunk, (index_id, run_id, ordinal))
                member.embedding = vector
            session.flush()
            completed = session.scalar(
                select(func.count())
                .select_from(IndexChunk)
                .where(
                    IndexChunk.index_id == index_id, IndexChunk.embedding.is_not(None)
                )
            )
            job.embedded_count = completed
            job.failures = 0
            job.execution_token = None
            job.updated_at = now()
            job.dispatched_at = None
            job.status = "succeeded" if completed == job.chunk_count else "queued"
            if job.status == "succeeded":
                job.finished_at = now()
            session.commit()
    except Exception as exc:
        transient = isinstance(exc, (OSError, SQLAlchemyError)) or (
            isinstance(exc, embeddings.EmbeddingError) and exc.transient
        )
        message = (
            str(exc)
            if isinstance(exc, embeddings.EmbeddingError)
            else "Indexing interrupted or unavailable. Create a new index to retry after checking the service."
        )
        with Session(db_engine) as session:
            job = session.scalar(
                select(IndexVersion)
                .where(IndexVersion.id == index_id)
                .with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return
            job.failures += 1
            job.status = "queued" if transient and job.failures < 3 else "failed"
            job.error = message
            job.execution_token = None
            job.updated_at = job.dispatched_at = now()
            if job.status == "failed":
                job.finished_at = now()
            session.commit()


@celery.task(name="indexes.embed")
def index_documents(index_id: str):
    process_index(UUID(index_id))
