"""Existing-files ingestion use cases and durable state reads."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.connectors.existing_files import ExistingFilesConnector
from app.models.document import Document, ProcessingRun
from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun, IngestionRunItem, IngestionRunNode
from app.models.project import Project
from app.models.source import SourceRevision, WebsiteRunItem
from app.ingestion_content import (
    cleaner_for_node,
    chunker_version_for_node,
    derivation_identity,
    processing_identity,
)
from app.ingestion_content.extractors import extractor_version_for_settings
from app.pipelines.parsing import PARSER_VERSION
from app.providers import embeddings
from app.schemas.document import ProcessingConfig
from app.schemas.ingestion import (
    IngestionDestination,
    IngestionExecution,
    IngestionPreviewItem,
    IngestionPreviewRead,
    IngestionSourceInput,
)
from app.services import indexes, ingestion_execution, pipelines, source_snapshots
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


def _processing_spec(execution: IngestionExecution):
    if execution.schema_version == 1:
        return None
    extract = next(node for node in execution.nodes if node.type == "extract")
    clean = next(node for node in execution.nodes if node.type == "clean")
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    extract_value = extract.model_dump(mode="json", exclude={"id", "type"})
    clean_value = clean.model_dump(mode="json", exclude={"id", "type"})
    chunk_value = chunk.model_dump(mode="json", exclude={"id", "type"})
    cleaner_version = cleaner_for_node(clean).version
    extractor_version = extractor_version_for_settings(extract)
    value, config_hash = processing_identity(
        schema_version=execution.schema_version,
        extractor_version=extractor_version,
        cleaner_version=cleaner_version,
        chunker_version=chunker_version_for_node(chunk),
        extract=extract_value,
        clean=clean_value,
        chunk=chunk_value,
    )
    return (
        value,
        config_hash,
        derivation_identity(
            schema_version=execution.schema_version,
            extractor_version=extractor_version,
            cleaner_version=cleaner_version,
            extract=extract_value,
            clean=clean_value,
        ),
    )


def _compatible_processing(
    session: Session,
    document_id: UUID,
    execution: IngestionExecution,
    latest: ProcessingRun | None,
):
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    spec = _processing_spec(execution)
    if spec is None:
        return (
            latest
            if latest is not None
            and _processing_matches(latest, chunk.size, chunk.overlap)
            else None
        )
    _, config_hash, _ = spec
    return session.scalar(
        select(ProcessingRun)
        .where(
            ProcessingRun.document_id == document_id,
            ProcessingRun.status == "succeeded",
            ProcessingRun.processing_config_hash == config_hash,
        )
        .order_by(ProcessingRun.version.desc())
        .limit(1)
    )


def _compatible_derivation(session, document_id, spec):
    if spec is None:
        return None
    derivation_hash = spec[2]
    return session.scalar(
        select(ProcessingRun)
        .where(
            ProcessingRun.document_id == document_id,
            ProcessingRun.status == "succeeded",
            ProcessingRun.derivation_config_hash == derivation_hash,
        )
        .order_by(ProcessingRun.version.desc())
        .limit(1)
    )


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


def _run_destination(session, project_id, publish, destination):
    if destination is None:
        return _knowledge_set(session, project_id, publish, create=True)
    if destination.kind == "existing":
        return indexes.get_knowledge_set(
            session, project_id, destination.knowledge_set_id
        )
    session.execute(
        select(Project.id).where(Project.id == project_id).with_for_update()
    )
    existing = session.scalar(
        select(KnowledgeSet).where(
            KnowledgeSet.project_id == project_id,
            KnowledgeSet.name == destination.name,
        )
    )
    if existing is not None:
        raise HTTPException(
            409, "An index with this name already exists. Select it explicitly."
        )
    result = KnowledgeSet(project_id=project_id, name=destination.name)
    session.add(result)
    session.flush()
    return result


def preview(session: Session, project_id: UUID, execution: IngestionExecution):
    project(session, project_id)
    selected, chunk, _ = _document_selection(execution)
    items = []
    for source_node_id, document_id in selected:
        connector = ExistingFilesConnector(session, project_id)
        document = session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.project_id == project_id,
                Document.origin_kind == "upload",
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
        compatible = None
        robust = execution.schema_version == 2
        active = latest is not None and latest.status in ("queued", "running")
        if not active and (robust or (latest and latest.status == "succeeded")):
            compatible = _compatible_processing(session, document.id, execution, latest)
        included = not active and (robust or compatible is not None)
        if latest is None and not robust:
            reason = "Process this file successfully before ingestion."
        elif active:
            reason = "Wait for the active processing run to finish."
        elif latest is not None and latest.status != "succeeded" and not robust:
            reason = "The latest processing run did not succeed. Retry it first."
        elif compatible:
            reason = f"Ready; processing version {compatible.version} will be reused."
        elif robust and latest is None:
            reason = (
                "Ready; ingestion will create the initial schema-v2 processing version."
            )
        elif robust and latest is not None and latest.status != "succeeded":
            reason = (
                "Ready; ingestion will retry the immutable upload with the saved "
                "schema-v2 extraction settings."
            )
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
                processing_run_id=(
                    compatible.id if compatible else latest.id if latest else None
                ),
                processing_version=(
                    compatible.version
                    if compatible
                    else latest.version
                    if latest
                    else None
                ),
                chunk_count=(
                    compatible.chunk_count
                    if compatible
                    else latest.chunk_count
                    if latest
                    else 0
                ),
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


def _add_node_states(
    session: Session, run: IngestionRun, execution: IngestionExecution
):
    for ordinal, node in enumerate(execution.nodes):
        session.add(
            IngestionRunNode(
                run_id=run.id,
                project_id=run.project_id,
                node_id=node.id,
                node_type=node.type,
                ordinal=ordinal,
                status="queued",
            )
        )


def start_run(
    session: Session,
    project_id: UUID,
    pipeline_id: UUID,
    version_id: UUID,
    *,
    trigger_kind: str = "manual",
    schedule_id: UUID | None = None,
    source_input: IngestionSourceInput | None = None,
    destination: IngestionDestination | None = None,
    reuse_stored: bool | None = None,
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
    sources = [node for node in execution.nodes if node.type == "source"]
    remote_kind = sources[0].config.kind if sources else None
    snapshot_requested = source_input is not None and source_input.kind == "snapshot"
    legacy_reuse = source_input is None and reuse_stored is True
    if remote_kind in ("website", "s3", "notion", "confluence") and all(
        source.config.kind == remote_kind for source in sources
    ):
        publish = next(node for node in execution.nodes if node.type == "publish_index")
        knowledge_set = _run_destination(session, project_id, publish, destination)
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
        if legacy_reuse and knowledge_set.current_ready_index_id is None:
            raise HTTPException(
                409,
                "Run this source pipeline once before reprocessing stored artifacts.",
            )
        prior_index = None
        selected_snapshot = None
        if legacy_reuse:
            prior_index = session.get(
                IndexVersion, knowledge_set.current_ready_index_id
            )
            prior_run = (
                session.get(IngestionRun, prior_index.ingestion_run_id)
                if prior_index is not None and prior_index.ingestion_run_id is not None
                else None
            )
            if (
                prior_run is None
                or prior_run.snapshot.get("source_kind") != remote_kind
            ):
                raise HTTPException(
                    409,
                    "The current index does not contain reusable artifacts for this source.",
                )
            prior_execution = IngestionExecution.model_validate(
                prior_run.snapshot["execution"]
            )
            prior_sources = {
                source.id: source.config.model_dump(mode="json")
                for source in prior_execution.nodes
                if source.type == "source"
            }
            current_sources = {
                source.id: source.config.model_dump(mode="json") for source in sources
            }
            if current_sources != prior_sources:
                raise HTTPException(
                    409,
                    "Source settings changed. Refresh the source before reprocessing stored artifacts.",
                )
            if prior_index.source_snapshot_id is not None:
                selected_snapshot = source_snapshots.require_compatible(
                    session,
                    project_id,
                    prior_index.source_snapshot_id,
                    execution,
                )
        elif snapshot_requested:
            selected_snapshot = source_snapshots.require_compatible(
                session,
                project_id,
                source_input.source_snapshot_id,
                execution,
            )
        effective_source_input = (
            {
                "kind": "snapshot",
                "source_snapshot_id": str(selected_snapshot.id),
            }
            if selected_snapshot is not None
            else {"kind": "refresh"}
        )
        run = IngestionRun(
            project_id=project_id,
            pipeline_version_id=version.id,
            knowledge_set_id=knowledge_set.id,
            schedule_id=schedule_id,
            trigger_kind=trigger_kind,
            stage="discovering",
            progress=0,
            discovered_count=0,
            snapshot={
                "source_kind": remote_kind,
                "pipeline_id": str(pipeline.id),
                "pipeline_version_id": str(version.id),
                "pipeline_version": version.version,
                "execution": execution.model_dump(mode="json"),
                "knowledge_set_id": str(knowledge_set.id),
                "knowledge_set_name": knowledge_set.name,
                "prior_ready_index_id": (
                    str(knowledge_set.current_ready_index_id)
                    if knowledge_set.current_ready_index_id
                    else None
                ),
                "source_input": effective_source_input,
                "reuse_stored": legacy_reuse,
                "embedding": embeddings.configured().model_dump(mode="json"),
            },
        )
        session.add(run)
        session.flush()
        _add_node_states(session, run, execution)
        if selected_snapshot is not None:
            run.source_snapshot_id = selected_snapshot.id
        elif legacy_reuse:
            run.source_snapshot_id = prior_index.source_snapshot_id
        else:
            source_snapshots.create_collecting(session, project_id, run, execution)
        session.commit()
        session.refresh(run)
        return read_run(session, run)
    if any(source.config.kind != "existing_files" for source in sources):
        raise HTTPException(409, "An ingestion run cannot mix source connector kinds.")
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
    optional_by_source = {
        source.id: set(source.config.optional_document_ids) for source in sources
    }
    for source_node_id, document_id in sorted(selected, key=lambda value: value[1]):
        document = session.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.project_id == project_id,
                Document.origin_kind == "upload",
            )
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
        if latest is None and execution.schema_version == 1:
            raise HTTPException(
                409, f"Process {document.filename} successfully before ingestion."
            )
        if latest is not None and latest.status in ("queued", "running"):
            raise HTTPException(
                409, f"Wait for {document.filename}'s active processing run to finish."
            )
        if (
            latest is not None
            and latest.status != "succeeded"
            and execution.schema_version == 1
        ):
            raise HTTPException(
                409, f"Retry {document.filename}'s failed processing run first."
            )
        compatible = _compatible_processing(session, document.id, execution, latest)
        processing_created = compatible is None
        if processing_created:
            spec = _processing_spec(execution)
            reusable = _compatible_derivation(session, document.id, spec)
            processing = ProcessingRun(
                document_id=document.id,
                version=(latest.version if latest is not None else 0) + 1,
                **ProcessingConfig(
                    chunk_size=chunk.size, overlap=chunk.overlap
                ).model_dump(),
                parser_version=(
                    spec[0]["versions"]["extractor"] if spec else PARSER_VERSION
                ),
                config_version=(
                    "ingestion-v2" if execution.schema_version == 2 else "characters-v1"
                ),
                processing_config=spec[0] if spec else None,
                processing_config_hash=spec[1] if spec else None,
                derivation_config_hash=spec[2] if spec else None,
                reused_from_processing_run_id=(reusable.id if reusable else None),
            )
            session.add(processing)
            session.flush()
        else:
            processing = compatible
        item_values.append(
            dict(
                project_id=project_id,
                document_id=document.id,
                source_node_id=source_node_id,
                processing_run_id=processing.id,
                processing_created=processing_created,
                is_optional=document.id in optional_by_source[source_node_id],
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
                "is_optional": document.id in optional_by_source[source_node_id],
            }
        )
    ready = [item for item in item_values if item["status"] == "ready"]
    run = IngestionRun(
        project_id=project_id,
        pipeline_version_id=version.id,
        knowledge_set_id=knowledge_set.id,
        schedule_id=schedule_id,
        trigger_kind=trigger_kind,
        stage="processing" if len(ready) != len(item_values) else "indexing",
        progress=int(40 * len(ready) / len(item_values)),
        discovered_count=len(item_values),
        processed_count=len(ready),
        chunk_count=sum(item["chunk_count"] for item in ready),
        snapshot={
            "pipeline_id": str(pipeline.id),
            "pipeline_version_id": str(version.id),
            "pipeline_version": version.version,
            "source_kind": "existing_files",
            "execution": execution.model_dump(mode="json"),
            "knowledge_set_id": str(knowledge_set.id),
            "knowledge_set_name": knowledge_set.name,
            "processing": processing_snapshot,
            "embedding": embeddings.configured().model_dump(mode="json"),
        },
    )
    session.add(run)
    session.flush()
    _add_node_states(session, run, execution)
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
    results = []
    for run, set_name, index_id, index_version in rows:
        node_states = session.scalars(
            select(IngestionRunNode)
            .where(IngestionRunNode.run_id == run.id)
            .order_by(IngestionRunNode.ordinal)
        ).all()
        outcome_counts = dict(
            session.execute(
                select(WebsiteRunItem.outcome, func.count())
                .where(WebsiteRunItem.run_id == run.id)
                .group_by(WebsiteRunItem.outcome)
            ).all()
        )
        results.append(
            {
                **{
                    column.name: getattr(run, column.name)
                    for column in IngestionRun.__table__.columns
                    if column.name
                    not in ("execution_token", "snapshot", "dispatched_at")
                },
                "knowledge_set_name": set_name,
                "published_index_id": index_id,
                "published_index_version": index_version,
                "node_states": [
                    {
                        "node_id": state.node_id,
                        "node_type": state.node_type,
                        "ordinal": state.ordinal,
                        "status": state.status,
                        "started_at": state.started_at,
                        "finished_at": state.finished_at,
                    }
                    for state in node_states
                ],
                "new_count": outcome_counts.get("new", 0),
                "changed_count": outcome_counts.get("changed", 0),
                "unchanged_count": outcome_counts.get("unchanged", 0),
                "removed_count": outcome_counts.get("removed", 0),
            }
        )
    return results


def read_run(session: Session, run: IngestionRun):
    return _run_rows(session, select(IngestionRun).where(IngestionRun.id == run.id))[0]


def list_runs(
    session: Session,
    project_id: UUID,
    limit: int,
    offset: int,
    *,
    pipeline_version_id: UUID | None = None,
):
    project(session, project_id)
    conditions = [IngestionRun.project_id == project_id]
    if pipeline_version_id is not None:
        conditions.append(IngestionRun.pipeline_version_id == pipeline_version_id)
    total = session.scalar(
        select(func.count()).select_from(IngestionRun).where(*conditions)
    )
    items = _run_rows(
        session,
        select(IngestionRun)
        .where(*conditions)
        .order_by(IngestionRun.created_at.desc(), IngestionRun.id.desc())
        .limit(limit)
        .offset(offset),
    )
    return dict(items=items, total=total, limit=limit, offset=offset)


def list_items(
    session: Session, project_id: UUID, run_id: UUID, limit: int, offset: int
):
    run = get_run(session, project_id, run_id)
    source_kind = run.snapshot.get("source_kind")
    if source_kind in ("website", "s3", "notion", "confluence"):
        query = (
            select(WebsiteRunItem)
            .where(
                WebsiteRunItem.run_id == run_id,
                WebsiteRunItem.project_id == project_id,
            )
            .order_by(WebsiteRunItem.ordinal)
        )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(query.limit(limit).offset(offset)).all()
        revisions = {
            revision.id: revision
            for revision in session.scalars(
                select(SourceRevision).where(
                    SourceRevision.id.in_(
                        [
                            item.source_revision_id
                            for item in rows
                            if item.source_revision_id
                        ]
                    )
                )
            ).all()
        }
        return dict(
            items=[
                {
                    "source_kind": source_kind,
                    **{
                        column.name: getattr(item, column.name)
                        for column in WebsiteRunItem.__table__.columns
                        if column.name not in ("run_id", "project_id", "created_at")
                    },
                    "processing_versions": (
                        revisions[item.source_revision_id].extraction_config.get(
                            "versions"
                        )
                        if item.source_revision_id in revisions
                        else None
                    ),
                    "processing_run_id": (
                        revisions[item.source_revision_id].processing_run_id
                        if item.source_revision_id in revisions
                        else None
                    ),
                }
                for item in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
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
                source_kind="existing_files",
                document_id=document.id,
                filename=document.filename,
                content_hash=document.content_hash,
                media_type=document.media_type,
                source_node_id=item.source_node_id,
                processing_run_id=processing.id,
                processing_version=processing.version,
                processing_created=item.processing_created,
                is_optional=item.is_optional,
                status=item.status,
                chunk_count=item.chunk_count,
                error=item.error,
                duplicate_decision=item.duplicate_decision,
                processing_versions=(
                    processing.processing_config.get("versions")
                    if processing.processing_config
                    else None
                ),
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
    ingestion_execution.mark_terminal(session, run.id, "cancelled")
    source_snapshots.mark_terminal(
        session,
        run.source_snapshot_id,
        "cancelled",
        "Collection was cancelled before a complete source snapshot was ready.",
    )
    session.execute(
        update(WebsiteRunItem)
        .where(WebsiteRunItem.run_id == run.id)
        .values(status="cancelled", updated_at=func.now())
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
