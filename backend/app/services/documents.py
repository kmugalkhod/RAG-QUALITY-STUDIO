import hashlib
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk
from app.models.ingestion import IngestionRunItem
from app.models.project import Project
from app.pipelines.parsing import PARSER_VERSION, ProcessingError
from app.ingestion_content.processing import IngestionStageError
from app.ingestion_content.extractors.pdf import detect_media_type
from app.schemas.document import DocumentRead, ProcessingConfig, RunRead


def project(session: Session, project_id: UUID):
    result = session.get(Project, project_id)
    if result is None:
        raise HTTPException(404, "Project not found.")
    return result


def document(session: Session, project_id: UUID, document_id: UUID):
    result = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.project_id == project_id,
            Document.origin_kind == "upload",
        )
    )
    if result is None:
        raise HTTPException(404, "Document not found in this project.")
    return result


def run(session: Session, project_id: UUID, document_id: UUID, run_id: UUID):
    document(session, project_id, document_id)
    result = session.scalar(
        select(ProcessingRun).where(
            ProcessingRun.id == run_id, ProcessingRun.document_id == document_id
        )
    )
    if result is None:
        raise HTTPException(404, "Processing run not found in this document.")
    return result


def upload(session: Session, project_id: UUID, file: UploadFile):
    project(session, project_id)
    filename = file.filename or ""
    if not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename):
        raise HTTPException(422, "Filename must contain 1–255 printable characters.")
    extension = Path(filename).suffix.lower()
    if extension not in {".txt", ".pdf"}:
        raise HTTPException(415, "Upload a PDF or UTF-8 TXT file.")
    # Content is authoritative; MIME supplied by browsers is not trusted.
    root = settings.storage_path
    name = uuid4().hex
    temporary = root / (name + ".part")
    final = root / name
    commit_started = False
    try:
        root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with temporary.open("xb") as output:
            while block := file.file.read(65536):
                size += len(block)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        413, "File exceeds the configured upload size limit."
                    )
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if size == 0:
            raise HTTPException(422, "The uploaded file is empty.")
        expected_media_type = "text/plain" if extension == ".txt" else "application/pdf"
        detected_media_type = detect_media_type(temporary)
        if detected_media_type != expected_media_type:
            raise HTTPException(
                422, "The file bytes do not match the selected PDF or TXT filename."
            )
        os.replace(temporary, final)
        # Persist the directory entry before committing its database reference.
        descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        result = Document(
            project_id=project_id,
            filename=filename,
            storage_name=name,
            media_type=detected_media_type,
            content_hash=digest.hexdigest(),
            size_bytes=size,
        )
        session.add(result)
        session.flush()
        response = DocumentRead.model_validate(result)
        commit_started = True
        session.commit()
        return response
    except ProcessingError as exc:
        raise HTTPException(422, str(exc)) from None
    except IngestionStageError as exc:
        raise HTTPException(422, exc.message) from None
    except OSError:
        raise HTTPException(
            503, "File storage unavailable. Please try again."
        ) from None
    finally:
        # A failed/ambiguous DB commit can leave an orphan file, never a missing
        # committed file. Remove known pre-commit files; preserve ambiguous commits.
        for path in [temporary] + ([final] if not commit_started else []):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logging.warning(
                    "Upload cleanup unavailable; inspect orphan files offline."
                )
        session.rollback()


def paginate(session, query, limit, offset):
    total = session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    return {
        "items": session.scalars(query.limit(limit).offset(offset)).all(),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def list_documents(session, project_id, limit, offset):
    project(session, project_id)
    result = paginate(
        session,
        select(Document)
        .where(Document.project_id == project_id, Document.origin_kind == "upload")
        .order_by(Document.created_at.desc(), Document.id.desc()),
        limit,
        offset,
    )
    items = []
    for doc in result["items"]:
        item = DocumentRead.model_validate(doc)
        latest = session.scalar(
            select(ProcessingRun)
            .where(ProcessingRun.document_id == doc.id)
            .order_by(ProcessingRun.version.desc())
            .limit(1)
        )
        item.latest_run = RunRead.model_validate(latest) if latest else None
        items.append(item)
    result["items"] = items
    return result


def remove(session: Session, project_id: UUID, document_id: UUID):
    result = session.scalar(
        select(Document)
        .where(
            Document.id == document_id,
            Document.project_id == project_id,
            Document.origin_kind == "upload",
        )
        .with_for_update()
    )
    if result is None:
        raise HTTPException(404, "Document not found in this project.")

    runs = session.scalars(
        select(ProcessingRun).where(ProcessingRun.document_id == result.id)
    ).all()
    if any(run.status in {"queued", "running"} for run in runs):
        raise HTTPException(
            409, "Cancel the active processing run before deleting this document."
        )

    run_ids = [run.id for run in runs]
    if run_ids and session.scalar(
        select(IndexChunk.index_id).where(IndexChunk.run_id.in_(run_ids)).limit(1)
    ):
        raise HTTPException(
            409,
            "This document is used by an immutable collection and cannot be deleted.",
        )
    if session.scalar(
        select(IngestionRunItem.run_id)
        .where(IngestionRunItem.document_id == result.id)
        .limit(1)
    ):
        raise HTTPException(
            409,
            "This document is used by an ingestion run and cannot be deleted.",
        )

    stored = settings.storage_path / result.storage_name
    staged = settings.storage_path / f"{result.storage_name}.deleting-{uuid4().hex}"
    moved = False
    try:
        if stored.exists():
            os.replace(stored, staged)
            moved = True
        if run_ids:
            session.execute(delete(Chunk).where(Chunk.run_id.in_(run_ids)))
            session.execute(delete(ProcessingRun).where(ProcessingRun.id.in_(run_ids)))
        session.delete(result)
        session.commit()
    except OSError:
        session.rollback()
        if moved:
            try:
                os.replace(staged, stored)
            except OSError:
                logging.error(
                    "Document delete rollback could not restore stored file %s.",
                    result.id,
                )
        raise HTTPException(
            503, "File storage unavailable. The document was not deleted."
        ) from None
    except IntegrityError:
        session.rollback()
        if moved:
            try:
                os.replace(staged, stored)
            except OSError:
                logging.error(
                    "Document delete rollback could not restore stored file %s.",
                    result.id,
                )
        raise HTTPException(
            409, "The document is still in use and could not be deleted."
        ) from None

    if moved:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            logging.warning(
                "Deleted document file cleanup unavailable; inspect orphan storage offline."
            )
    return {"deleted": True}


def start(
    session: Session, project_id: UUID, document_id: UUID, config: ProcessingConfig
):
    # Serialize version allocation and reject concurrent starts.
    locked = session.scalar(
        select(Document)
        .where(
            Document.id == document_id,
            Document.project_id == project_id,
            Document.origin_kind == "upload",
        )
        .with_for_update()
    )
    if locked is None:
        raise HTTPException(404, "Document not found in this project.")
    active = session.scalar(
        select(ProcessingRun.id).where(
            ProcessingRun.document_id == document_id,
            ProcessingRun.status.in_(["queued", "running"]),
        )
    )
    if active:
        raise HTTPException(409, "This document already has an active processing run.")
    version = (
        session.scalar(
            select(func.max(ProcessingRun.version)).where(
                ProcessingRun.document_id == document_id
            )
        )
        or 0
    ) + 1
    result = ProcessingRun(
        document_id=document_id,
        version=version,
        **config.model_dump(),
        parser_version=PARSER_VERSION,
    )
    session.add(result)
    session.commit()
    session.refresh(result)
    # PostgreSQL is the durable queue. A dispatcher sends the ID after commit.
    return result


def list_runs(session, project_id, document_id, limit, offset):
    document(session, project_id, document_id)
    return paginate(
        session,
        select(ProcessingRun)
        .where(ProcessingRun.document_id == document_id)
        .order_by(ProcessingRun.version.desc()),
        limit,
        offset,
    )


def list_chunks(session, project_id, document_id, run_id, limit, offset):
    result = run(session, project_id, document_id, run_id)
    if result.status != "succeeded":
        raise HTTPException(
            409, "Chunks are available only after successful processing."
        )
    return paginate(
        session,
        select(Chunk).where(Chunk.run_id == run_id).order_by(Chunk.ordinal),
        limit,
        offset,
    )


def cancel(session, project_id, document_id, run_id):
    result = run(session, project_id, document_id, run_id)
    # Conditional update prevents a cancellation from overwriting completion.
    session.execute(
        update(ProcessingRun)
        .where(
            ProcessingRun.id == result.id,
            ProcessingRun.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            updated_at=func.now(),
            finished_at=func.now(),
            error="Cancelled. In-flight parsing may continue until its next checkpoint; no chunks will be published.",
        )
    )
    session.commit()
    session.refresh(result)
    return result
