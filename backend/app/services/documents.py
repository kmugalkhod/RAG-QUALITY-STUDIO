import hashlib
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Chunk, Document, ProcessingRun
from app.models.project import Project
from app.pipelines.parsing import PARSER_VERSION, ProcessingError, validate_text
from app.schemas.document import DocumentRead, ProcessingConfig, RunRead


def project(session: Session, project_id: UUID):
    result = session.get(Project, project_id)
    if result is None:
        raise HTTPException(404, "Project not found.")
    return result


def document(session: Session, project_id: UUID, document_id: UUID):
    result = session.scalar(
        select(Document).where(
            Document.id == document_id, Document.project_id == project_id
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
        if extension == ".txt":
            validate_text(temporary.read_bytes())
        else:
            with temporary.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    raise HTTPException(422, "The file is not a PDF.")
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
            media_type="text/plain" if extension == ".txt" else "application/pdf",
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
        .where(Document.project_id == project_id)
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


def start(
    session: Session, project_id: UUID, document_id: UUID, config: ProcessingConfig
):
    document(session, project_id, document_id)
    # Serialize version allocation and reject concurrent starts.
    session.execute(
        select(Document).where(Document.id == document_id).with_for_update()
    )
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
