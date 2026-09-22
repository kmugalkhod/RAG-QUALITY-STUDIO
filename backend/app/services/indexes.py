from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk, IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.project import Project
from app.models.source import SourceSnapshot
from app.providers import embeddings
from app.schemas.index import IndexCreate, RetrievalRequest
from app.services.documents import paginate, project


DEFAULT_KNOWLEDGE_SET_NAME = "Uploaded documents"
MAX_INDEX_CHUNKS = 50_000


def get_index(session: Session, project_id: UUID, index_id: UUID):
    result = session.scalar(
        select(IndexVersion).where(
            IndexVersion.id == index_id, IndexVersion.project_id == project_id
        )
    )
    if result is None:
        raise HTTPException(404, "Index not found in this project.")
    return result


def get_knowledge_set(session: Session, project_id: UUID, knowledge_set_id: UUID):
    result = session.scalar(
        select(KnowledgeSet).where(
            KnowledgeSet.id == knowledge_set_id,
            KnowledgeSet.project_id == project_id,
        )
    )
    if result is None:
        raise HTTPException(404, "Knowledge set not found in this project.")
    return result


def default_knowledge_set(session: Session, project_id: UUID):
    result = session.scalar(
        select(KnowledgeSet).where(
            KnowledgeSet.project_id == project_id,
            KnowledgeSet.name == DEFAULT_KNOWLEDGE_SET_NAME,
        )
    )
    if result is None:
        result = KnowledgeSet(project_id=project_id, name=DEFAULT_KNOWLEDGE_SET_NAME)
        session.add(result)
        session.flush()
    return result


def snapshot_latest_processing_runs(
    session: Session, project_id: UUID, document_ids: list[UUID] | None = None
) -> list[UUID]:
    if document_ids is not None and len(set(document_ids)) != len(document_ids):
        raise HTTPException(422, "Document IDs must be unique.")
    if document_ids is not None:
        found = session.scalars(
            select(Document.id).where(
                Document.project_id == project_id,
                Document.origin_kind == "upload",
                Document.id.in_(document_ids),
            )
        ).all()
        if len(found) != len(document_ids):
            raise HTTPException(
                404, "A selected document was not found in this project."
            )
    latest = (
        select(
            ProcessingRun.document_id, func.max(ProcessingRun.version).label("version")
        )
        .join(Document)
        .where(
            Document.project_id == project_id,
            Document.origin_kind == "upload",
            ProcessingRun.status == "succeeded",
        )
    )
    if document_ids is not None:
        latest = latest.where(Document.id.in_(document_ids))
    latest = latest.group_by(ProcessingRun.document_id).subquery()
    run_ids = session.scalars(
        select(ProcessingRun.id)
        .join(
            latest,
            (ProcessingRun.document_id == latest.c.document_id)
            & (ProcessingRun.version == latest.c.version),
        )
        .order_by(ProcessingRun.document_id)
    ).all()
    if document_ids is not None and len(run_ids) != len(document_ids):
        raise HTTPException(
            409, "Process every selected document successfully before indexing."
        )
    if not run_ids:
        raise HTTPException(
            409, "Process at least one document successfully before indexing."
        )
    return list(run_ids)


def create_index_from_processing_runs(
    session: Session,
    project_id: UUID,
    knowledge_set_id: UUID,
    processing_run_ids: list[UUID],
    *,
    ingestion_run_id: UUID | None = None,
    source_snapshot_id: UUID | None = None,
    commit: bool = True,
):
    if not processing_run_ids:
        raise HTTPException(422, "Select at least one processing run to index.")
    if len(set(processing_run_ids)) != len(processing_run_ids):
        raise HTTPException(422, "Processing run IDs must be unique.")
    project(session, project_id)
    config = embeddings.configured()
    knowledge_set = session.scalar(
        select(KnowledgeSet)
        .where(
            KnowledgeSet.id == knowledge_set_id,
            KnowledgeSet.project_id == project_id,
        )
        .with_for_update()
    )
    if knowledge_set is None:
        raise HTTPException(404, "Knowledge set not found in this project.")
    if session.scalar(
        select(IndexVersion.id).where(
            IndexVersion.knowledge_set_id == knowledge_set_id,
            IndexVersion.status.in_(["queued", "running"]),
        )
    ):
        raise HTTPException(
            409, "This knowledge set already has an active indexing job."
        )
    runs = session.execute(
        select(ProcessingRun.id, ProcessingRun.status)
        .join(Document)
        .where(
            ProcessingRun.id.in_(processing_run_ids), Document.project_id == project_id
        )
    ).all()
    if len(runs) != len(processing_run_ids):
        raise HTTPException(404, "A processing run was not found in this project.")
    if any(status != "succeeded" for _, status in runs):
        raise HTTPException(409, "Only successful processing runs can be indexed.")
    members = session.execute(
        select(Chunk.run_id, Chunk.ordinal)
        .where(Chunk.run_id.in_(processing_run_ids))
        .order_by(Chunk.run_id, Chunk.ordinal)
        .limit(MAX_INDEX_CHUNKS + 1)
    ).all()
    if not members:
        raise HTTPException(409, "Selected processing runs contain no chunks.")
    represented_runs = {run_id for run_id, _ in members}
    if represented_runs != set(processing_run_ids):
        raise HTTPException(409, "Every selected processing run must contain chunks.")
    if len(members) > MAX_INDEX_CHUNKS:
        raise HTTPException(
            422,
            "An index supports at most 50,000 chunks. Increase chunk size or use a smaller project.",
        )
    version = (
        session.scalar(
            select(func.max(IndexVersion.version)).where(
                IndexVersion.knowledge_set_id == knowledge_set_id
            )
        )
        or 0
    ) + 1
    result = IndexVersion(
        project_id=project_id,
        knowledge_set_id=knowledge_set_id,
        ingestion_run_id=ingestion_run_id,
        source_snapshot_id=source_snapshot_id,
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
    if commit:
        session.commit()
        session.refresh(result)
    else:
        session.flush()
    return result


def create_index(session: Session, project_id: UUID, data: IndexCreate):
    project(session, project_id)
    session.execute(select(Project).where(Project.id == project_id).with_for_update())
    knowledge_set = (
        get_knowledge_set(session, project_id, data.knowledge_set_id)
        if data.knowledge_set_id
        else default_knowledge_set(session, project_id)
    )
    if session.scalar(
        select(IngestionRun.id).where(
            IngestionRun.knowledge_set_id == knowledge_set.id,
            IngestionRun.status.in_(["queued", "running"]),
        )
    ):
        raise HTTPException(
            409, "This knowledge set already has an active ingestion run."
        )
    run_ids = snapshot_latest_processing_runs(session, project_id, data.document_ids)
    return create_index_from_processing_runs(
        session, project_id, knowledge_set.id, run_ids
    )


def _index_rows(session, statement):
    run_count = (
        select(func.count(func.distinct(IndexChunk.run_id)))
        .where(IndexChunk.index_id == IndexVersion.id)
        .correlate(IndexVersion)
        .scalar_subquery()
    )
    rows = session.execute(
        statement.add_columns(
            KnowledgeSet.name,
            KnowledgeSet.current_ready_index_id,
            run_count,
            IngestionRun,
            SourceSnapshot,
            PipelineVersion,
            Pipeline,
        )
        .join(KnowledgeSet, KnowledgeSet.id == IndexVersion.knowledge_set_id)
        .outerjoin(IngestionRun, IngestionRun.id == IndexVersion.ingestion_run_id)
        .outerjoin(SourceSnapshot, SourceSnapshot.id == IndexVersion.source_snapshot_id)
        .outerjoin(
            PipelineVersion, PipelineVersion.id == IngestionRun.pipeline_version_id
        )
        .outerjoin(Pipeline, Pipeline.id == PipelineVersion.pipeline_id)
    ).all()
    results = []
    for (
        index,
        knowledge_set_name,
        current_ready_index_id,
        processing_run_count,
        ingestion_run,
        source_snapshot,
        pipeline_version,
        pipeline,
    ) in rows:
        execution = (
            (ingestion_run.snapshot or {}).get("execution", {}) if ingestion_run else {}
        )
        chunk = next(
            (
                node
                for node in execution.get("nodes", [])
                if node.get("type") == "chunk"
            ),
            None,
        )
        results.append(
            {
                **{
                    column.name: getattr(index, column.name)
                    for column in IndexVersion.__table__.columns
                },
                "knowledge_set_name": knowledge_set_name,
                "processing_run_count": processing_run_count,
                "is_current": current_ready_index_id == index.id,
                "source_kind": (ingestion_run.snapshot or {}).get("source_kind")
                if ingestion_run
                else None,
                "source_snapshot": {
                    "id": source_snapshot.id,
                    "snapshot_number": source_snapshot.snapshot_number,
                    "status": source_snapshot.status,
                    "source_kind": source_snapshot.source_kind,
                    "included_count": source_snapshot.included_count,
                    "collected_at": source_snapshot.collected_at,
                }
                if source_snapshot
                else None,
                "ingestion_pipeline": {
                    "id": pipeline.id,
                    "name": pipeline.name,
                    "version": pipeline_version.version,
                }
                if pipeline and pipeline_version
                else None,
                "processing_summary": {
                    "unit": chunk.get("unit", "characters"),
                    "size": chunk["size"],
                    "overlap": chunk["overlap"],
                    "config_version": chunk.get("config_version"),
                }
                if chunk
                else None,
            }
        )
    return results


def read_index(session: Session, index: IndexVersion):
    return _index_rows(
        session, select(IndexVersion).where(IndexVersion.id == index.id)
    )[0]


def list_indexes(
    session, project_id, limit, offset, knowledge_set_id: UUID | None = None
):
    project(session, project_id)
    conditions = [IndexVersion.project_id == project_id]
    if knowledge_set_id is not None:
        get_knowledge_set(session, project_id, knowledge_set_id)
        conditions.append(IndexVersion.knowledge_set_id == knowledge_set_id)
    total = session.scalar(
        select(func.count()).select_from(IndexVersion).where(*conditions)
    )
    items = _index_rows(
        session,
        select(IndexVersion)
        .where(*conditions)
        .order_by(
            IndexVersion.knowledge_set_id,
            IndexVersion.version.desc(),
            IndexVersion.id.desc(),
        )
        .limit(limit)
        .offset(offset),
    )
    return dict(items=items, total=total, limit=limit, offset=offset)


def list_knowledge_sets(session, project_id, limit, offset):
    project(session, project_id)
    return paginate(
        session,
        select(KnowledgeSet)
        .where(KnowledgeSet.project_id == project_id)
        .order_by(KnowledgeSet.created_at, KnowledgeSet.id),
        limit,
        offset,
    )


def list_index_records(session, project_id, index_id, limit, offset):
    index = get_index(session, project_id, index_id)
    total = session.scalar(
        select(func.count())
        .select_from(IndexChunk)
        .where(IndexChunk.index_id == index.id)
    )
    rows = session.execute(
        select(IndexChunk, Chunk, ProcessingRun, Document)
        .join(
            Chunk,
            (Chunk.run_id == IndexChunk.run_id) & (Chunk.ordinal == IndexChunk.ordinal),
        )
        .join(ProcessingRun, ProcessingRun.id == Chunk.run_id)
        .join(Document, Document.id == ProcessingRun.document_id)
        .where(IndexChunk.index_id == index.id, Document.project_id == project_id)
        .order_by(Document.filename, IndexChunk.run_id, IndexChunk.ordinal)
        .limit(limit)
        .offset(offset)
    ).all()
    items = []
    for member, chunk, run, document in rows:
        embedding = member.embedding.tolist() if member.embedding is not None else []
        provenance = chunk.provenance or {}
        items.append(
            dict(
                run_id=member.run_id,
                ordinal=member.ordinal,
                document_id=document.id,
                filename=document.filename,
                processing_version=run.version,
                page_number=chunk.page_number,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                text=chunk.text,
                source_url=provenance.get("canonical_url"),
                section_path=provenance.get("section_path") or [],
                dimensions=member.dimensions,
                embedded=bool(embedding),
                embedding_norm=(sum(value * value for value in embedding) ** 0.5)
                if embedding
                else None,
                embedding_preview=embedding[:8],
            )
        )
    return dict(items=items, total=total, limit=limit, offset=offset)


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
    from app.pipelines.retrieval import search

    items, diagnostics = search(session, project_id, index, request, config)
    return dict(
        index_id=index.id,
        index_version=index.version,
        embedding_config=config,
        retrieval=request.retrieval,
        diagnostics=diagnostics,
        items=items,
        score_semantics=(
            "Cosine distance: lower is closer; this is not confidence."
            if request.retrieval.mode == "vector"
            else "Lexical and weighted RRF scores: higher ranks first. Scores are not confidence and are not comparable across search modes."
        ),
    )
