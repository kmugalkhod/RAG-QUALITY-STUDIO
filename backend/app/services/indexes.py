from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk, IndexVersion
from app.models.project import Project
from app.providers import embeddings
from app.schemas.index import RetrievalRequest
from app.services.documents import paginate, project


def get_index(session: Session, project_id: UUID, index_id: UUID):
    result = session.scalar(
        select(IndexVersion).where(
            IndexVersion.id == index_id, IndexVersion.project_id == project_id
        )
    )
    if result is None:
        raise HTTPException(404, "Index not found in this project.")
    return result


def create_index(session, project_id):
    project(session, project_id)
    config = embeddings.configured()
    session.execute(select(Project).where(Project.id == project_id).with_for_update())
    if session.scalar(
        select(IndexVersion.id).where(
            IndexVersion.project_id == project_id,
            IndexVersion.status.in_(["queued", "running"]),
        )
    ):
        raise HTTPException(409, "This project already has an active indexing job.")
    # A single snapshot chooses the latest successful processing version per source.
    latest = (
        select(
            ProcessingRun.document_id, func.max(ProcessingRun.version).label("version")
        )
        .join(Document)
        .where(Document.project_id == project_id, ProcessingRun.status == "succeeded")
        .group_by(ProcessingRun.document_id)
        .subquery()
    )
    runs = select(ProcessingRun.id).join(
        latest,
        (ProcessingRun.document_id == latest.c.document_id)
        & (ProcessingRun.version == latest.c.version),
    )
    members = session.execute(
        select(Chunk.run_id, Chunk.ordinal).where(Chunk.run_id.in_(runs)).limit(50001)
    ).all()
    if not members:
        raise HTTPException(
            409, "Process at least one document successfully before indexing."
        )
    if len(members) > 50000:
        raise HTTPException(
            422,
            "An index supports at most 50,000 chunks. Increase chunk size or use a smaller project.",
        )
    version = (
        session.scalar(
            select(func.max(IndexVersion.version)).where(
                IndexVersion.project_id == project_id
            )
        )
        or 0
    ) + 1
    result = IndexVersion(
        project_id=project_id,
        version=version,
        dimensions=config.dimensions,
        embedding_config=config.model_dump(),
        chunk_count=len(members),
    )
    session.add(result)
    session.flush()
    for start in range(0, len(members), 500):
        session.execute(
            insert(IndexChunk),
            [
                dict(
                    index_id=result.id,
                    run_id=r,
                    ordinal=o,
                    dimensions=config.dimensions,
                )
                for r, o in members[start : start + 500]
            ],
        )
    session.commit()
    session.refresh(result)
    return result


def list_indexes(session, project_id, limit, offset):
    project(session, project_id)
    return paginate(
        session,
        select(IndexVersion)
        .where(IndexVersion.project_id == project_id)
        .order_by(IndexVersion.version.desc()),
        limit,
        offset,
    )


def cancel_index(session, project_id, index_id):
    result = get_index(session, project_id, index_id)
    session.execute(
        update(IndexVersion)
        .where(
            IndexVersion.id == result.id, IndexVersion.status.in_(["queued", "running"])
        )
        .values(
            status="cancelled",
            execution_token=None,
            updated_at=func.now(),
            finished_at=func.now(),
            error="Cancelled. An in-flight provider request may finish, but its results cannot publish.",
        )
    )
    session.commit()
    session.refresh(result)
    return result


def retrieve(session, project_id, request: RetrievalRequest):
    index = get_index(session, project_id, request.index_id)
    if index.status != "succeeded":
        raise HTTPException(
            409, "Select a ready index. Partial indexes cannot be searched."
        )
    config = embeddings.EmbeddingConfig.model_validate(index.embedding_config)
    provider = embeddings.provider_for(config)
    vector = embeddings.validate_vectors(
        provider.embed([request.query]), 1, index.dimensions
    )[0]
    distance = IndexChunk.embedding.cosine_distance(vector).label("cosine_distance")
    rows = session.execute(
        select(Chunk, ProcessingRun, Document, distance)
        .select_from(IndexChunk)
        .join(
            Chunk,
            (Chunk.run_id == IndexChunk.run_id) & (Chunk.ordinal == IndexChunk.ordinal),
        )
        .join(ProcessingRun, ProcessingRun.id == Chunk.run_id)
        .join(Document, Document.id == ProcessingRun.document_id)
        .where(
            IndexChunk.index_id == index.id,
            Document.project_id == project_id,
            IndexChunk.embedding.is_not(None),
        )
        .order_by(distance, Chunk.run_id, Chunk.ordinal)
        .limit(request.top_k)
    ).all()
    return dict(
        index_id=index.id,
        index_version=index.version,
        embedding_config=config,
        items=[
            dict(
                rank=rank,
                document_id=doc.id,
                filename=doc.filename,
                content_hash=doc.content_hash,
                run_id=run.id,
                processing_version=run.version,
                ordinal=chunk.ordinal,
                page_number=chunk.page_number,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                text=chunk.text,
                cosine_distance=distance,
            )
            for rank, (chunk, run, doc, distance) in enumerate(rows, 1)
        ],
    )
