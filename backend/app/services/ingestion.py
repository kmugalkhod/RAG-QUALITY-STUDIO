"""Existing-files ingestion use cases and durable state reads."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.connectors.existing_files import ExistingFilesConnector
from app.models.document import Document, ProcessingRun
from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun, IngestionRunItem
from app.pipelines.parsing import PARSER_VERSION
from app.providers import embeddings
from app.schemas.document import ProcessingConfig
from app.schemas.ingestion import (
    IngestionExecution,
    IngestionPreviewItem,
    IngestionPreviewRead,
)
from app.services import indexes, pipelines
from app.services.documents import project


def _nodes(execution: IngestionExecution):
    source_nodes = [node for node in execution.nodes if node.type == "source"]
    if any(node.config.kind != "existing_files" for node in source_nodes):
        raise HTTPException(409, "Only Existing Files sources can run in this phase.")
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    publish = next(node for node in execution.nodes if node.type == "publish_index")
    return source_nodes, chunk, publish


def _document_selection(execution: IngestionExecution):
    source_nodes, chunk, publish = _nodes(execution)
    selected: list[tuple[str, UUID]] = [
        (source.id, document_id)
        for source in source_nodes
        for document_id in source.config.document_ids
    ]
    ids = [document_id for _, document_id in selected]
    if len(set(ids)) != len(ids):
        raise HTTPException(
            422, "A document can appear in only one Existing Files source node."
        )
    return selected, chunk, publish


def _knowledge_set(session, project_id, publish, *, create: bool):
    if publish.knowledge_set_id is not None:
        result = indexes.get_knowledge_set(
            session, project_id, publish.knowledge_set_id
        )
        if result.name != publish.knowledge_set_name:
            raise HTTPException(
                409, "The saved knowledge-set name no longer matches its identity."
            )
        return result
    result = session.scalar(
        select(KnowledgeSet).where(
            KnowledgeSet.project_id == project_id,
            KnowledgeSet.name == publish.knowledge_set_name,
        )
    )
    if result is None and create:
        result = KnowledgeSet(project_id=project_id, name=publish.knowledge_set_name)
        session.add(result)
        session.flush()
    if result is None:
        raise HTTPException(404, "Knowledge set not found in this project.")
    return result


def preview(session: Session, project_id: UUID, execution: IngestionExecution):
    project(session, project_id)
    selected, chunk, _ = _document_selection(execution)
    items = []
    for source_node_id, document_id in selected:
        connector = ExistingFilesConnector(session, project_id)
        document = session.scalar(
            select(Document).where(
                Document.id == document_id, Document.project_id == project_id
            )
        )
        if document is None:
            raise HTTPException(
                404, "One or more source documents were not found in this project."
            )
        latest = session.scalar(
            select(ProcessingRun)
            .where(ProcessingRun.document_id == document.id)
            .order_by(ProcessingRun.version.desc())
            .limit(1)
        )
        included = latest is not None and latest.status == "succeeded"
        if latest is None:
            reason = "Process this file successfully before ingestion."
        elif latest.status in ("queued", "running"):
            reason = "Wait for the active processing run to finish."
        elif latest.status != "succeeded":
            reason = "The latest processing run did not succeed. Retry it first."
        elif _processing_matches(latest, chunk.size, chunk.overlap):
            reason = f"Ready; processing version {latest.version} will be reused."
        else:
            reason = (
                "Ready; ingestion will create a new processing version with "
                f"{chunk.size} character chunks and {chunk.overlap} overlap."
            )
        discovered = connector._item(document)
        items.append(
            IngestionPreviewItem(
                source_node_id=source_node_id,
                document_id=document.id,
                filename=document.filename,
                media_type=document.media_type,
                content_hash=document.content_hash,
                size_bytes=int(discovered.metadata["size_bytes"]),
                included=included,
                reason=reason,
                processing_run_id=latest.id if latest else None,
                processing_version=latest.version if latest else None,
                chunk_count=latest.chunk_count if latest else 0,
            )
        )
    included_count = sum(item.included for item in items)
    return IngestionPreviewRead(
        items=items,
        discovered_count=len(items),
        included_count=included_count,
        excluded_count=len(items) - included_count,
    )


def _processing_matches(run: ProcessingRun, size: int, overlap: int):
    return (
        run.status == "succeeded"
        and run.chunk_size == size
        and run.overlap == overlap
        and run.config_version == "characters-v1"
        and run.parser_version == PARSER_VERSION
    )


def start_run(
    session: Session,
    project_id: UUID,
    pipeline_id: UUID,
    version_id: UUID,
):
    pipeline = pipelines.get_pipeline(session, project_id, pipeline_id)
    if pipeline.kind != "ingestion":
        raise HTTPException(
            409, "Answer pipeline versions cannot run through the ingestion endpoint."
        )
    version = pipelines.get_version(session, project_id, pipeline_id, version_id)
    execution = IngestionExecution.model_validate(version.execution)
    pipelines.validate_ingestion(session, project_id, execution)
    embeddings.configured()
    selected, chunk, publish = _document_selection(execution)
    knowledge_set = _knowledge_set(session, project_id, publish, create=True)
    session.execute(
        select(KnowledgeSet)
        .where(KnowledgeSet.id == knowledge_set.id)
        .with_for_update()
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

    item_values = []
    processing_snapshot = []
    for source_node_id, document_id in sorted(selected, key=lambda value: value[1]):
        document = session.scalar(
            select(Document)
            .where(Document.id == document_id, Document.project_id == project_id)
            .with_for_update()
        )
        if document is None:
            raise HTTPException(
                404, "One or more source documents were not found in this project."
            )
        latest = session.scalar(
            select(ProcessingRun)
            .where(ProcessingRun.document_id == document.id)
            .order_by(ProcessingRun.version.desc())
            .limit(1)
        )
        if latest is None:
            raise HTTPException(
                409, f"Process {document.filename} successfully before ingestion."
            )
        if latest.status in ("queued", "running"):
            raise HTTPException(
                409, f"Wait for {document.filename}'s active processing run to finish."
            )
        if latest.status != "succeeded":
            raise HTTPException(
                409, f"Retry {document.filename}'s failed processing run first."
            )
        processing_created = not _processing_matches(latest, chunk.size, chunk.overlap)
        if processing_created:
            processing = ProcessingRun(
                document_id=document.id,
                version=latest.version + 1,
                **ProcessingConfig(
                    chunk_size=chunk.size, overlap=chunk.overlap
                ).model_dump(),
                parser_version=PARSER_VERSION,
            )
            session.add(processing)
            session.flush()
        else:
            processing = latest
        item_values.append(
            dict(
                project_id=project_id,
                document_id=document.id,
                source_node_id=source_node_id,
                processing_run_id=processing.id,
                processing_created=processing_created,
                status="processing" if processing_created else "ready",
                chunk_count=0 if processing_created else processing.chunk_count,
            )
        )
        processing_snapshot.append(
            {
                "document_id": str(document.id),
                "content_hash": document.content_hash,
                "processing_run_id": str(processing.id),
                "processing_version": processing.version,
                "processing_created": processing_created,
            }
        )
    ready = [item for item in item_values if item["status"] == "ready"]
    run = IngestionRun(
        project_id=project_id,
        pipeline_version_id=version.id,
        knowledge_set_id=knowledge_set.id,
        stage="processing" if len(ready) != len(item_values) else "indexing",
        progress=int(40 * len(ready) / len(item_values)),
        discovered_count=len(item_values),
        processed_count=len(ready),
        chunk_count=sum(item["chunk_count"] for item in ready),
        snapshot={
            "pipeline_id": str(pipeline.id),
            "pipeline_version_id": str(version.id),
            "pipeline_version": version.version,
            "execution": execution.model_dump(mode="json"),
            "knowledge_set_id": str(knowledge_set.id),
            "knowledge_set_name": knowledge_set.name,
            "processing": processing_snapshot,
            "embedding": embeddings.configured().model_dump(mode="json"),
        },
    )
    session.add(run)
    session.flush()
    for item in item_values:
        session.add(IngestionRunItem(run_id=run.id, **item))
    session.commit()
    session.refresh(run)
    return read_run(session, run)


def get_run(session: Session, project_id: UUID, run_id: UUID):
    result = session.scalar(
        select(IngestionRun).where(
            IngestionRun.id == run_id, IngestionRun.project_id == project_id
        )
    )
    if result is None:
        raise HTTPException(404, "Ingestion run not found in this project.")
    return result


def _run_rows(session: Session, statement):
    rows = session.execute(
        statement.add_columns(KnowledgeSet.name, IndexVersion.id, IndexVersion.version)
        .join(KnowledgeSet, KnowledgeSet.id == IngestionRun.knowledge_set_id)
        .outerjoin(IndexVersion, IndexVersion.ingestion_run_id == IngestionRun.id)
    ).all()
    return [
        {
            **{
                column.name: getattr(run, column.name)
                for column in IngestionRun.__table__.columns
                if column.name not in ("execution_token", "snapshot", "dispatched_at")
            },
            "knowledge_set_name": set_name,
            "published_index_id": index_id,
            "published_index_version": index_version,
        }
        for run, set_name, index_id, index_version in rows
    ]


def read_run(session: Session, run: IngestionRun):
    return _run_rows(session, select(IngestionRun).where(IngestionRun.id == run.id))[0]


def list_runs(session: Session, project_id: UUID, limit: int, offset: int):
    project(session, project_id)
    total = session.scalar(
        select(func.count())
        .select_from(IngestionRun)
        .where(IngestionRun.project_id == project_id)
    )
    items = _run_rows(
        session,
        select(IngestionRun)
        .where(IngestionRun.project_id == project_id)
        .order_by(IngestionRun.created_at.desc(), IngestionRun.id.desc())
        .limit(limit)
        .offset(offset),
    )
    return dict(items=items, total=total, limit=limit, offset=offset)


def list_items(
    session: Session, project_id: UUID, run_id: UUID, limit: int, offset: int
):
    get_run(session, project_id, run_id)
    query = (
        select(IngestionRunItem, Document, ProcessingRun)
        .join(Document, Document.id == IngestionRunItem.document_id)
        .join(ProcessingRun, ProcessingRun.id == IngestionRunItem.processing_run_id)
        .where(
            IngestionRunItem.run_id == run_id,
            IngestionRunItem.project_id == project_id,
        )
        .order_by(Document.filename, Document.id)
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(query.limit(limit).offset(offset)).all()
    return dict(
        items=[
            dict(
                document_id=document.id,
                filename=document.filename,
                content_hash=document.content_hash,
                media_type=document.media_type,
                source_node_id=item.source_node_id,
                processing_run_id=processing.id,
                processing_version=processing.version,
                processing_created=item.processing_created,
                status=item.status,
                chunk_count=item.chunk_count,
                error=item.error,
                updated_at=item.updated_at,
            )
            for item, document, processing in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def cancel_run(session: Session, project_id: UUID, run_id: UUID):
    run = get_run(session, project_id, run_id)
    if run.status not in ("queued", "running"):
        return read_run(session, run)
    session.execute(
        update(IngestionRun)
        .where(
            IngestionRun.id == run.id,
            IngestionRun.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error=(
                "Cancelled. In-flight processing or embedding may finish, but this run cannot publish."
            ),
            updated_at=func.now(),
            finished_at=func.now(),
        )
    )
    session.execute(
        update(IngestionRunItem)
        .where(IngestionRunItem.run_id == run.id)
        .values(status="cancelled", updated_at=func.now())
    )
    created_processing = select(IngestionRunItem.processing_run_id).where(
        IngestionRunItem.run_id == run.id,
        IngestionRunItem.processing_created.is_(True),
    )
    session.execute(
        update(ProcessingRun)
        .where(
            ProcessingRun.id.in_(created_processing),
            ProcessingRun.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Cancelled with its ingestion run; no chunks were published.",
            updated_at=func.now(),
            finished_at=func.now(),
        )
    )
    session.execute(
        update(IndexVersion)
        .where(
            IndexVersion.ingestion_run_id == run.id,
            IndexVersion.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Cancelled with its ingestion run; this index was not published.",
            updated_at=func.now(),
            finished_at=func.now(),
        )
    )
    session.commit()
    session.refresh(run)
    return read_run(session, run)
