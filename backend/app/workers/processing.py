import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import engine
from app.ingestion_content import (
    IngestionStageError,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.extractors import extract_document
from app.ingestion_content.quality import quality_allows_publication
from app.models.document import Chunk, Document, ProcessingRun
from app.pipelines.parsing import MAX_CHUNKS, ProcessingError, pages, windows
from app.schemas.ingestion import ChunkNodeV2, CleanNodeV2, ExtractNodeV2
from app.services import ingestion_execution
from app.services.derivations import (
    link_reused_derivations,
    persist_derivations,
    reusable_cleaned_document,
)
from app.workers.celery_app import celery


def now():
    return datetime.now(timezone.utc)


def _chunk_cleaned(job, cleaned, config, on_stage):
    chunk_config = TypeAdapter(ChunkNodeV2).validate_python(
        {"id": "chunk", "type": "chunk", **config.get("chunk", {})}
    )
    on_stage("chunk")
    chunking = chunk_cleaned_document(
        cleaned,
        chunk_config,
        provenance={"processing_versions": config.get("versions", {})},
    )
    if len(chunking.chunks) > MAX_CHUNKS:
        raise IngestionStageError(
            "chunk",
            "chunk_limit_exceeded",
            "Processing exceeds the 50,000 chunk limit. Increase chunk size or reduce overlap.",
        )
    if sum(len(value.text) for value in chunking.chunks) > 10_000_000:
        raise IngestionStageError(
            "chunk",
            "chunk_output_too_large",
            "Chunk text exceeds the 10,000,000 character output limit. Reduce overlap.",
        )
    chunks = [value.as_record() | {"run_id": job.id} for value in chunking.chunks]
    if not chunks:
        raise IngestionStageError(
            "chunk", "no_text", "The document contains no text after cleaning."
        )
    encoded = json.dumps(
        [
            {
                "ordinal": value["ordinal"],
                "page_number": value["page_number"],
                "start_char": value["start_char"],
                "end_char": value["end_char"],
                "text": value["text"],
                "embedding_text": value["embedding_text"],
                "token_count": value["token_count"],
                "embedding_token_count": value["embedding_token_count"],
                "chunk_role": value["chunk_role"],
                "parent_ordinal": value["parent_ordinal"],
                "findings": value["findings"],
            }
            for value in chunks
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return chunks, hashlib.sha256(encoded).hexdigest(), chunking.spans


def _v2_chunks(job, path, media, title, on_stage, cancelled=None):
    config = job.processing_config or {}
    extract_config = ExtractNodeV2.model_validate(
        {"id": "extract", "type": "extract", **config.get("extract", {})}
    )
    clean_config = CleanNodeV2.model_validate(
        {"id": "clean", "type": "clean", **config.get("clean", {})}
    )
    cleaner = cleaner_for_node(clean_config)
    extracted, extractor_version = extract_document(
        path,
        media,
        title,
        extract_config,
        cancelled=cancelled,
    )
    if not quality_allows_publication(
        extract_config.quality_policy, extracted.measurements.quality_decision
    ):
        code = (
            "quality_warning_blocked"
            if extracted.measurements.quality_decision == "warn"
            else "quality_rejected"
        )
        raise IngestionStageError(
            "extract",
            code,
            "Extraction did not satisfy the saved quality policy. Review the source "
            "and extraction settings before retrying.",
        )
    on_stage("clean")
    cleaned = clean_document(
        extracted,
        clean_config,
        cleaner,
        extractor_version=extractor_version,
        configuration_hash=job.processing_config_hash,
    )
    total_characters = cleaned.measurements.character_count
    length_violation = cleaner.length_violation(total_characters, clean_config)
    if length_violation == "too_short":
        raise IngestionStageError(
            "clean",
            "text_too_short",
            "Cleaned text is shorter than the configured minimum.",
        )
    if length_violation == "too_long":
        raise IngestionStageError(
            "clean",
            "text_too_long",
            "Cleaned text exceeds the configured maximum.",
        )
    chunks, output_hash, spans = _chunk_cleaned(job, cleaned, config, on_stage)
    return (
        chunks,
        output_hash,
        extracted,
        cleaned,
        spans,
        extractor_version,
    )


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
        processing_config = job.processing_config
        processing_config_hash = job.processing_config_hash
        reused_from_processing_run_id = job.reused_from_processing_run_id
        document_id = doc.id
        project_id = doc.project_id
        title = doc.filename
        session.commit()
    ingestion_execution.transition_for_processing_run(db_engine, run_id, "extract")

    def cancelled():
        with Session(db_engine) as cancellation_session:
            current = cancellation_session.get(ProcessingRun, run_id)
            return (
                current is None
                or current.status != "running"
                or current.execution_token != token
            )

    try:
        output_hash = None
        canonical = None
        if processing_config and processing_config.get("schema_version") == 2:

            def stage(value):
                ingestion_execution.transition_for_processing_run(
                    db_engine, run_id, value
                )

            scoped_job = SimpleNamespace(
                id=run_id,
                processing_config=processing_config,
                processing_config_hash=processing_config_hash,
            )
            if reused_from_processing_run_id is not None:
                with Session(db_engine) as session:
                    cleaned, _ = reusable_cleaned_document(
                        session, reused_from_processing_run_id
                    )
                stage("clean")
                chunks, output_hash, spans = _chunk_cleaned(
                    scoped_job, cleaned, processing_config, stage
                )
                canonical = ("reused", reused_from_processing_run_id, spans)
            else:
                chunks, output_hash, extracted, cleaned, spans, extractor_version = (
                    _v2_chunks(
                        scoped_job,
                        path,
                        media,
                        title,
                        stage,
                        cancelled,
                    )
                )
                canonical = (
                    "new",
                    extracted,
                    cleaned,
                    spans,
                    extractor_version,
                )
        else:
            chunks = []
            chunk_characters = 0
            processing_phase_started = False
            for page, value, completed, total in pages(path, media):
                if not processing_phase_started:
                    ingestion_execution.transition_for_processing_run(
                        db_engine, run_id, "clean"
                    )
                    ingestion_execution.transition_for_processing_run(
                        db_engine, run_id, "chunk"
                    )
                    processing_phase_started = True
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
                            progress=min(95, int(95 * completed / total)),
                            updated_at=now(),
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
            if canonical is not None:
                if canonical[0] == "reused":
                    _, source_run_id, spans = canonical
                    link_reused_derivations(
                        session,
                        processing_run_id=run_id,
                        source_processing_run_id=source_run_id,
                        document_id=document_id,
                        project_id=project_id,
                        spans=spans,
                    )
                else:
                    _, extracted, cleaned, spans, extractor_version = canonical
                    persist_derivations(
                        session,
                        project_id=project_id,
                        document_id=document_id,
                        processing_run_id=run_id,
                        extracted=extracted,
                        cleaned=cleaned,
                        extractor_version=extractor_version,
                        spans=spans,
                    )
            job.status = "succeeded"
            job.chunk_count = len(chunks)
            job.progress = 100
            job.output_hash = output_hash
            job.finished_at = job.updated_at = now()
            job.execution_token = None
            session.commit()
    except Exception as exc:
        # No raw source text, paths or driver errors are persisted or logged.
        transient = isinstance(exc, (OSError, SQLAlchemyError))
        message = (
            str(exc)
            if isinstance(exc, (ProcessingError, IngestionStageError))
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
