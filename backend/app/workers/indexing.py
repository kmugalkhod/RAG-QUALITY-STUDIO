"""One bounded embedding batch per Celery delivery; PostgreSQL owns checkpoints."""

from contextlib import ExitStack
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.ingestion_content.chunking import EMBEDDING_INPUT_BYTES
from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun
from app.providers import embeddings
from app.providers.rate_limit import request_share
from app.services import ingestion_execution, provider_credentials
from app.workers.celery_app import celery
from app.workers.handoff import hand_off
from app.workers.processing import now

# Spec 0012 C6/D7: up to 64 passages per request within a byte budget far below
# the provider's per-request token limit (OpenAI allows 2,048 inputs and 300,000
# tokens; UTF-8 bytes are an upper bound on tokens).
BATCH_SIZE = 64
MAX_BATCH_BYTES = 192_000
# Indexing takes at most this share of the per-minute request budget, leaving the
# rest for Playground and answer queries (45 of the default 60).
INDEXING_REQUEST_SHARE = 0.75
THROTTLE_DELAY_SECONDS = 20
RETRY_DELAY_SECONDS = 15
# Spec 0012 D7: continuous throttling for this long fails the index.
THROTTLE_LIMIT = timedelta(minutes=15)
THROTTLED_TOO_LONG = (
    "The embedding provider kept refusing requests (rate limit) for 15 minutes, "
    "so indexing stopped. Nothing new was published; start the run again later."
)


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
        ingestion_run_id = job.ingestion_run_id
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
                        Chunk.page_number,
                        Document.filename,
                    )
                    .join(
                        Chunk,
                        (Chunk.run_id == IndexChunk.run_id)
                        & (Chunk.ordinal == IndexChunk.ordinal),
                    )
                    .join(ProcessingRun, ProcessingRun.id == Chunk.run_id)
                    .join(Document, Document.id == ProcessingRun.document_id)
                    .where(
                        IndexChunk.index_id == index_id, IndexChunk.embedding.is_(None)
                    )
                    .order_by(IndexChunk.run_id, IndexChunk.ordinal)
                    .limit(BATCH_SIZE)
                ).all()
                batch = []
                total = 0
                for row in candidates:
                    size = len(row.text.encode("utf-8"))
                    if batch and total + size > MAX_BATCH_BYTES:
                        break
                    batch.append(row)
                    total += size
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
            for row in missing:
                size = len(row.text.encode("utf-8"))
                if size > EMBEDDING_INPUT_BYTES:
                    # Name the passage instead of the adapter's generic refusal
                    # (spec 0012 A8). Not retried: the text cannot change.
                    page = f", page {row.page_number}" if row.page_number else ""
                    raise embeddings.EmbeddingError(
                        f"Passage {row.ordinal + 1} of {row.filename}{page} is "
                        f"{size:,} bytes, more than the embedding provider's "
                        f"{EMBEDDING_INPUT_BYTES:,}-byte limit. Lower the Chunk "
                        "maximum size and run again."
                    )
            usage = None
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
                # Identical texts in one batch are sent once (spec 0012 C6).
                texts = list(dict.fromkeys(row.text for row in missing))
                with request_share(INDEXING_REQUEST_SHARE):
                    raw, usage = embeddings.embed_with_usage(provider, texts)
                values = embeddings.validate_vectors(raw, len(texts), config.dimensions)
                by_text = dict(zip(texts, values, strict=True))
                vectors.update(
                    {(row.run_id, row.ordinal): by_text[row.text] for row in missing}
                )
            with Session(db_engine) as session:
                # Lock the parent ingestion run before the index, the same order as
                # cancellation and coordination, so a run cannot become terminal
                # between this check and publishing its index.
                if ingestion_run_id is not None:
                    parent_status = session.scalar(
                        select(IngestionRun.status)
                        .where(IngestionRun.id == ingestion_run_id)
                        .with_for_update()
                    )
                job = session.scalar(
                    select(IndexVersion)
                    .where(IndexVersion.id == index_id)
                    .with_for_update()
                )
                if usage is not None:
                    # Paid work is recorded even when the run ended during the
                    # request (spec 0012 A11). Unknown stays unknown: one
                    # unreported request makes the total NULL.
                    job.embedding_tokens = (
                        None
                        if job.embedding_tokens is None or usage.tokens is None
                        else job.embedding_tokens + usage.tokens
                    )
                    job.embedding_cost_usd = (
                        None
                        if job.embedding_cost_usd is None or usage.cost_usd is None
                        else job.embedding_cost_usd + Decimal(str(usage.cost_usd))
                    )
                if job.status != "running" or job.execution_token != token:
                    session.commit()
                    return
                if ingestion_run_id is not None and parent_status not in (
                    "queued",
                    "running",
                ):
                    job.status = "cancelled"
                    job.execution_token = None
                    job.error = "Stopped because the parent ingestion run ended; this index was not published."
                    job.updated_at = job.finished_at = now()
                    session.commit()
                    return
                # One bulk update by primary key, not one load per row (C6).
                if vectors:
                    session.execute(
                        update(IndexChunk),
                        [
                            {
                                "index_id": index_id,
                                "run_id": run_id,
                                "ordinal": ordinal,
                                "embedding": vector,
                            }
                            for (run_id, ordinal), vector in vectors.items()
                        ],
                    )
                if job.reused_vector_count is not None:
                    job.reused_vector_count += len(batch) - len(missing)
                job.throttled_since = None
                # A running count; the fenced token means each row is counted once.
                # The whole index is counted only to confirm completion.
                completed = job.embedded_count + len(vectors)
                if completed >= job.chunk_count:
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
                    current = now()
                    if (
                        job.throttled_since is not None
                        and current - job.throttled_since >= THROTTLE_LIMIT
                    ):
                        job.status = "failed"
                        job.error = THROTTLED_TOO_LONG
                        job.dispatched_at = None
                        job.finished_at = current
                        session.commit()
                        return None
                    # Waiting for request budget does not consume a retry.
                    job.throttled_since = job.throttled_since or current
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
