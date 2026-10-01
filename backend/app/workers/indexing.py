"""One bounded embedding batch per Celery delivery; PostgreSQL owns checkpoints."""

from contextlib import ExitStack
from uuid import UUID, uuid4
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.providers import embeddings
from app.services import ingestion_execution, provider_credentials
from app.workers.celery_app import celery
from app.workers.handoff import hand_off
from app.workers.processing import now

BATCH_SIZE = 16
MAX_BATCH_CHARACTERS = 24000
THROTTLE_DELAY_SECONDS = 20
RETRY_DELAY_SECONDS = 15


def process_index(index_id: UUID, db_engine=engine, send=None):
    """Embed one batch. With `send`, deliver the next batch or retry directly
    instead of waiting for the dispatcher's next pass."""
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid4()
    countdown = _process_batch(index_id, db_engine, token, send is not None)
    if send is not None and countdown is not None:
        hand_off(db_engine, IndexVersion, index_id, send, countdown or None)


def _process_batch(index_id: UUID, db_engine, token, handing_off) -> int | None:
    """Return a delay in seconds when the index should run again, else None."""
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
        ingestion_execution.transition_for_index(db_engine, job, "embed")
    with ExitStack() as credential_scope:
        try:
            with Session(db_engine) as session:
                credential_scope.enter_context(
                    provider_credentials.bound_for_project(session, project_id)
                )
            provider = embeddings.provider_for(config)
            with Session(db_engine) as session:
                candidates = session.execute(
                    select(
                        IndexChunk.run_id,
                        IndexChunk.ordinal,
                        func.coalesce(Chunk.embedding_text, Chunk.text).label("text"),
                        Chunk.embedding_text_hash,
                    )
                    .join(
                        Chunk,
                        (Chunk.run_id == IndexChunk.run_id)
                        & (Chunk.ordinal == IndexChunk.ordinal),
                    )
                    .where(
                        IndexChunk.index_id == index_id, IndexChunk.embedding.is_(None)
                    )
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
                # Exact text plus the complete embedding config, only within this
                # project. One indexed hash lookup serves the whole batch.
                old_chunk = aliased(Chunk)
                old_text = func.coalesce(old_chunk.embedding_text, old_chunk.text)
                hashes = {
                    row.embedding_text_hash
                    for row in batch
                    if row.embedding_text_hash is not None
                }
                cached = {}
                if hashes:
                    lookup = session.execute(
                        select(
                            old_chunk.embedding_text_hash,
                            old_text.label("text"),
                            IndexChunk.embedding,
                        )
                        .distinct(old_chunk.embedding_text_hash)
                        .join(
                            IndexChunk,
                            (IndexChunk.run_id == old_chunk.run_id)
                            & (IndexChunk.ordinal == old_chunk.ordinal),
                        )
                        .join(IndexVersion, IndexVersion.id == IndexChunk.index_id)
                        .join(ProcessingRun, ProcessingRun.id == old_chunk.run_id)
                        .join(Document, Document.id == ProcessingRun.document_id)
                        .where(
                            old_chunk.embedding_text_hash.in_(hashes),
                            IndexVersion.project_id == project_id,
                            Document.project_id == project_id,
                            IndexVersion.embedding_config == config.model_dump(),
                            IndexChunk.embedding.is_not(None),
                        )
                    )
                    cached = {row.embedding_text_hash: row for row in lookup}
                for row in batch:
                    hit = cached.get(row.embedding_text_hash)
                    if hit is not None and hit.text == row.text:
                        vectors[(row.run_id, row.ordinal)] = (
                            embeddings.validate_vectors(
                                [hit.embedding.tolist()], 1, config.dimensions
                            )[0]
                        )
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
                        IndexChunk.index_id == index_id,
                        IndexChunk.embedding.is_not(None),
                    )
                )
                job.embedded_count = completed
                job.failures = 0
                job.execution_token = None
                job.updated_at = now()
                job.status = "succeeded" if completed == job.chunk_count else "queued"
                # A worker hand-off counts as sent; the dispatcher only recovers it.
                job.dispatched_at = (
                    now() if handing_off and job.status == "queued" else None
                )
                if job.status == "succeeded":
                    ingestion_execution.transition_for_index(
                        db_engine, job, "publish_index"
                    )
                    job.finished_at = now()
                    session.execute(
                        update(KnowledgeSet)
                        .where(
                            KnowledgeSet.id == job.knowledge_set_id,
                            KnowledgeSet.project_id == job.project_id,
                        )
                        .values(current_ready_index_id=job.id)
                    )
                session.commit()
                return 0 if job.status == "queued" else None
        except Exception as exc:
            transient = isinstance(exc, (OSError, SQLAlchemyError)) or (
                isinstance(exc, embeddings.EmbeddingError) and exc.transient
            )
            throttled = isinstance(exc, embeddings.EmbeddingError) and exc.throttled
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
                job.execution_token = None
                job.error = message
                job.updated_at = job.dispatched_at = now()
                if throttled:
                    # Waiting for request budget does not consume a retry.
                    job.status = "queued"
                    session.commit()
                    return THROTTLE_DELAY_SECONDS
                job.failures += 1
                job.status = "queued" if transient and job.failures < 3 else "failed"
                if job.status == "failed":
                    job.finished_at = now()
                session.commit()
                return (
                    RETRY_DELAY_SECONDS * job.failures
                    if job.status == "queued"
                    else None
                )


def _send(index_id: UUID, countdown=None):
    index_documents.apply_async(args=[str(index_id)], countdown=countdown)


@celery.task(name="indexes.embed")
def index_documents(index_id: str):
    process_index(UUID(index_id), send=_send)
