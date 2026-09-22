"""Bounded coordinator for fenced Existing Files ingestion stages."""

from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.website import (
    PreviewOutcome,
    PriorWebsiteRevision,
    WebsiteArtifact,
    WebsiteConnector,
)
from app.connectors.s3 import S3Connector
from app.connectors.notion import NotionConnector
from app.connectors.confluence import ConfluenceConnector
from app.core.connection_secrets import ConnectionKeyring
from app.core.config import settings
from app.models.document import ProcessingRun
from app.models.index import IndexVersion
from app.models.ingestion import IngestionRun, IngestionRunItem
from app.models.source import (
    IndexSourceRevision,
    SourceItem,
    SourceRevision,
    WebsiteRunItem,
)
from app.pipelines.parsing import ProcessingError
from app.schemas.ingestion import IngestionExecution
from app.services import (
    connections,
    confluence_ingestion,
    indexes,
    notion_ingestion,
    s3_ingestion,
    source_snapshots,
    website_ingestion,
)
from app.workers.celery_app import celery
from app.workers.processing import now


def _fail(session: Session, job: IngestionRun, message: str):
    source_snapshots.mark_terminal(session, job.source_snapshot_id, "failed", message)
    job.status = "failed"
    job.execution_token = None
    job.error = message
    job.updated_at = job.finished_at = now()


def _cancel_unpublished_work(session: Session, run_id: UUID):
    created = select(IngestionRunItem.processing_run_id).where(
        IngestionRunItem.run_id == run_id,
        IngestionRunItem.processing_created.is_(True),
    )
    session.execute(
        update(ProcessingRun)
        .where(
            ProcessingRun.id.in_(created),
            ProcessingRun.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Stopped because the parent ingestion run failed.",
            updated_at=now(),
            finished_at=now(),
        )
    )
    session.execute(
        update(IndexVersion)
        .where(
            IndexVersion.ingestion_run_id == run_id,
            IndexVersion.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Stopped because the parent ingestion run failed.",
            updated_at=now(),
            finished_at=now(),
        )
    )


def _website_priors(session, job):
    index_id = job.snapshot.get("prior_ready_index_id")
    if not index_id:
        return {}, {}
    rows = session.execute(
        select(IndexSourceRevision.source_node_id, SourceItem, SourceRevision)
        .select_from(IndexSourceRevision)
        .join(SourceItem, SourceItem.id == IndexSourceRevision.source_item_id)
        .join(
            SourceRevision, SourceRevision.id == IndexSourceRevision.source_revision_id
        )
        .where(
            IndexSourceRevision.index_id == UUID(index_id),
            IndexSourceRevision.project_id == job.project_id,
            SourceItem.kind == "website",
        )
    ).all()
    revisions = {
        item.canonical_location: (revision, source_node_id)
        for source_node_id, item, revision in rows
    }
    priors = {}
    for location, (revision, _) in revisions.items():
        try:
            content = (
                settings.storage_path / revision.artifact_storage_name
            ).read_bytes()
        except OSError as exc:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="prior_artifact_unavailable",
                    message="A prior website artifact is unavailable for safe refresh.",
                    retryable=True,
                )
            ) from exc
        priors[location] = PriorWebsiteRevision(
            content=content,
            media_type=revision.media_type,
            etag=revision.etag,
            last_modified=revision.last_modified,
        )
    return priors, revisions


def _discover_website(run_id, db_engine, connector_factory):
    with Session(db_engine) as session:
        job = session.get(IngestionRun, run_id)
        execution = IngestionExecution.model_validate(job.snapshot["execution"])
        priors, revisions = _website_priors(session, job)
    if job.snapshot.get("reuse_stored"):
        results = []
        for source in [node for node in execution.nodes if node.type == "source"]:
            outcomes = []
            artifacts = []
            for location, (revision, source_node_id) in revisions.items():
                if source_node_id != source.id:
                    continue
                prior = priors[location]
                outcomes.append(
                    PreviewOutcome(
                        external_id=location,
                        display_name=location,
                        canonical_location=location,
                        media_type=revision.media_type,
                        status="included",
                        reason="Stored page selected for offline reprocessing.",
                        size_bytes=revision.size_bytes,
                        depth=(revision.provenance or {}).get("depth"),
                        provider_revision=revision.provider_revision,
                    )
                )
                artifacts.append(
                    WebsiteArtifact(
                        canonical_location=location,
                        content=prior.content,
                        media_type=prior.media_type,
                        etag=prior.etag,
                        last_modified=prior.last_modified,
                        validator_unchanged=True,
                        depth=(revision.provenance or {}).get("depth") or 0,
                    )
                )
            results.append((source.id, outcomes, artifacts))
        return execution, revisions, results
    results = []
    for source in [node for node in execution.nodes if node.type == "source"]:
        connector = connector_factory() if connector_factory else WebsiteConnector()
        outcomes, artifacts = connector.fetch_all(source.config, priors)
        results.append((source.id, outcomes, artifacts))
    return execution, revisions, results


def _credentialed_priors(session, job, kind):
    index_id = job.snapshot.get("prior_ready_index_id")
    if not index_id:
        return {}
    rows = session.execute(
        select(IndexSourceRevision.source_node_id, SourceItem, SourceRevision)
        .select_from(IndexSourceRevision)
        .join(SourceItem, SourceItem.id == IndexSourceRevision.source_item_id)
        .join(
            SourceRevision, SourceRevision.id == IndexSourceRevision.source_revision_id
        )
        .where(
            IndexSourceRevision.index_id == UUID(index_id),
            IndexSourceRevision.project_id == job.project_id,
            SourceItem.kind == kind,
        )
    ).all()
    return {
        (source_node_id, item.canonical_location): (item, revision)
        for source_node_id, item, revision in rows
    }


def _discover_credentialed(
    run_id,
    token,
    db_engine,
    connector_factory,
    *,
    kind,
    connector_type,
    persistence,
):
    with Session(db_engine) as session:
        job = session.get(IngestionRun, run_id)
        execution = IngestionExecution.model_validate(job.snapshot["execution"])
        priors = _credentialed_priors(session, job, kind)
        keyring = ConnectionKeyring.from_settings(settings)
        chunk = next(node for node in execution.nodes if node.type == "chunk")
        clean = next(node for node in execution.nodes if node.type == "clean")
        _, processing_hash = persistence.processing_configuration(chunk, clean)
        sources = [
            (
                source,
                connections.credentials_for_use(
                    session,
                    job.project_id,
                    source.config.connection_id,
                    kind,
                    keyring,
                ),
            )
            for source in execution.nodes
            if source.type == "source"
        ]

    # Never hold a database transaction open during bounded provider calls.
    results = []
    for source, credentials in sources:
        connector = (
            connector_factory(credentials)
            if connector_factory
            else connector_type(credentials)
        )
        if kind == "confluence":

            def cancelled():
                with Session(db_engine) as cancellation_session:
                    current = cancellation_session.get(IngestionRun, run_id)
                    return (
                        current is None
                        or current.status != "running"
                        or current.execution_token != token
                    )

            connector.cancellation_check = cancelled
        source_priors = {
            location: revision
            for (node_id, location), (_, revision) in priors.items()
            if node_id == source.id
        }
        outcomes, artifacts = connector.fetch_all(
            source.config, source_priors, processing_hash
        )
        results.append((source.id, source.config.connection_id, outcomes, artifacts))
    return execution, priors, results


def _advance_credentialed(
    run_id,
    token,
    db_engine,
    connector_factory,
    *,
    kind,
    label,
    connector_type,
    persistence,
):
    execution, prior_revisions, results = _discover_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind=kind,
        connector_type=connector_type,
        persistence=persistence,
    )
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    with Session(db_engine) as session:
        job = session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
        )
        if job.status != "running" or job.execution_token != token:
            return
        if session.scalar(
            select(WebsiteRunItem.run_id)
            .where(WebsiteRunItem.run_id == run_id)
            .limit(1)
        ):
            return
        ordinal = 0
        included = set()
        memberships = []
        seen_extracted = set()
        failed = 0
        for source_node_id, connection_id, outcomes, artifacts in results:
            artifact_by_location = {
                artifact.item.canonical_location: artifact for artifact in artifacts
            }
            for outcome in outcomes:
                if outcome.status != "included":
                    add_outcome = (
                        "failed" if outcome.status == "failed" else outcome.status
                    )
                    website_ingestion.add_run_item(
                        session,
                        run=job,
                        ordinal=ordinal,
                        source_node_id=source_node_id,
                        outcome=add_outcome,
                        reason=outcome.reason,
                        location=outcome.canonical_location,
                        display_name=outcome.display_name,
                        media_type=outcome.media_type,
                        error=outcome.error_code,
                    )
                    failed += outcome.status == "failed"
                    ordinal += 1
                    continue
                artifact = artifact_by_location[outcome.canonical_location]
                prior_entry = prior_revisions.get(
                    (source_node_id, artifact.item.canonical_location)
                )
                prior_item, prior = prior_entry if prior_entry else (None, None)
                if artifact.unchanged:
                    if prior is None or prior_item is None:
                        raise ConnectorFailure(
                            ConnectorIssue(
                                code="prior_revision_unavailable",
                                message=f"A prior {label} revision is unavailable for safe refresh.",
                                retryable=True,
                            )
                        )
                    source_item, revision = prior_item, prior
                    classification = "unchanged"
                    extracted_hash = revision.extracted_hash
                else:
                    (
                        source_item,
                        revision,
                        classification,
                        extracted_hash,
                        _stored_path,
                    ) = persistence.persist_artifact(
                        session,
                        job.project_id,
                        connection_id,
                        artifact,
                        chunk,
                        clean,
                        prior,
                    )
                if (
                    clean.exact_content_deduplication
                    and extracted_hash in seen_extracted
                ):
                    classification = "excluded"
                    reason = f"Extracted text duplicates another included {label}."
                else:
                    seen_extracted.add(extracted_hash)
                    included.add((source_node_id, artifact.item.canonical_location))
                    memberships.append((source_node_id, source_item, revision))
                    reason = f"{label.capitalize()} revision is {classification}."
                website_ingestion.add_run_item(
                    session,
                    run=job,
                    ordinal=ordinal,
                    source_node_id=source_node_id,
                    outcome=classification,
                    reason=reason,
                    location=artifact.item.canonical_location,
                    display_name=artifact.item.display_name,
                    media_type=artifact.item.media_type,
                    source_item=source_item,
                    revision=revision,
                )
                ordinal += 1
        for key, (item, revision) in prior_revisions.items():
            if key in included:
                continue
            source_node_id, location = key
            website_ingestion.add_run_item(
                session,
                run=job,
                ordinal=ordinal,
                source_node_id=source_node_id,
                outcome="removed",
                reason=f"Previously indexed {label} was not included by this refresh.",
                location=location,
                display_name=item.external_id,
                source_item=item,
                revision=revision,
                media_type=revision.media_type,
            )
            ordinal += 1
        job.discovered_count = ordinal
        job.failed_count = failed
        job.processed_count = ordinal - failed
        if failed:
            _fail(
                session,
                job,
                f"One or more required {label}s failed. The previous ready index remains current.",
            )
            session.commit()
            return
        if not memberships:
            raise HTTPException(
                409, f"{label.capitalize()} discovery found no indexable pages."
            )
        processing_ids = list(
            dict.fromkeys(revision.processing_run_id for _, _, revision in memberships)
        )
        index = indexes.create_index_from_processing_runs(
            session,
            job.project_id,
            job.knowledge_set_id,
            processing_ids,
            ingestion_run_id=job.id,
            commit=False,
        )
        session.execute(
            insert(IndexSourceRevision),
            [
                {
                    "index_id": index.id,
                    "source_revision_id": revision.id,
                    "source_item_id": item.id,
                    "source_node_id": source_node_id,
                    "project_id": job.project_id,
                }
                for source_node_id, item, revision in memberships
            ],
        )
        job.stage = "indexing"
        job.chunk_count = index.chunk_count
        job.progress = 40
        job.status = "queued"
        job.execution_token = None
        job.failures = 0
        job.dispatched_at = None
        job.updated_at = now()
        session.commit()


def _advance_s3(run_id, token, db_engine, connector_factory):
    return _advance_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind="s3",
        label="S3 object",
        connector_type=S3Connector,
        persistence=s3_ingestion,
    )


def _advance_notion(run_id, token, db_engine, connector_factory):
    return _advance_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind="notion",
        label="Notion page",
        connector_type=NotionConnector,
        persistence=notion_ingestion,
    )


def _advance_confluence(run_id, token, db_engine, connector_factory):
    return _advance_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind="confluence",
        label="Confluence page",
        connector_type=ConfluenceConnector,
        persistence=confluence_ingestion,
    )


def _advance_website(run_id, token, db_engine, connector_factory):
    execution, prior_revisions, results = _discover_website(
        run_id, db_engine, connector_factory
    )
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    with Session(db_engine) as session:
        job = session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
        )
        if job.status != "running" or job.execution_token != token:
            return
        if session.scalar(
            select(WebsiteRunItem.run_id)
            .where(WebsiteRunItem.run_id == run_id)
            .limit(1)
        ):
            return
        ordinal = 0
        included_locations = set()
        memberships = []
        seen_extracted = set()
        failed = 0
        for source_node_id, outcomes, artifacts in results:
            artifact_by_location = {
                artifact.canonical_location: artifact for artifact in artifacts
            }
            for outcome in outcomes:
                if outcome.status != "included":
                    add_outcome = (
                        "failed" if outcome.status == "failed" else outcome.status
                    )
                    website_ingestion.add_run_item(
                        session,
                        run=job,
                        ordinal=ordinal,
                        source_node_id=source_node_id,
                        outcome=add_outcome,
                        reason=outcome.reason,
                        location=outcome.canonical_location,
                        display_name=outcome.display_name,
                        media_type=outcome.media_type,
                        error=outcome.error_code,
                    )
                    failed += outcome.status == "failed"
                    ordinal += 1
                    continue
                artifact = artifact_by_location[outcome.canonical_location]
                prior_entry = prior_revisions.get(artifact.canonical_location)
                prior = prior_entry[0] if prior_entry else None
                source_item, revision, classification, extracted_hash, _stored_path = (
                    website_ingestion.persist_artifact(
                        session,
                        job.project_id,
                        artifact,
                        chunk,
                        clean,
                        prior,
                    )
                )
                if (
                    clean.exact_content_deduplication
                    and extracted_hash in seen_extracted
                ):
                    classification = "excluded"
                    reason = "Extracted text duplicates another included website page."
                else:
                    seen_extracted.add(extracted_hash)
                    included_locations.add(artifact.canonical_location)
                    memberships.append((source_node_id, source_item, revision))
                    reason = f"Website revision is {classification}."
                website_ingestion.add_run_item(
                    session,
                    run=job,
                    ordinal=ordinal,
                    source_node_id=source_node_id,
                    outcome=classification,
                    reason=reason,
                    location=artifact.canonical_location,
                    display_name=outcome.display_name,
                    media_type=artifact.media_type,
                    source_item=source_item,
                    revision=revision,
                )
                ordinal += 1
        for location, (revision, prior_source_node_id) in prior_revisions.items():
            if location in included_locations:
                continue
            item = session.get(SourceItem, revision.source_item_id)
            website_ingestion.add_run_item(
                session,
                run=job,
                ordinal=ordinal,
                source_node_id=prior_source_node_id,
                outcome="removed",
                reason="Previously indexed URL was not included by this refresh.",
                location=location,
                source_item=item,
                revision=revision,
                media_type=revision.media_type,
            )
            ordinal += 1
        job.discovered_count = ordinal
        job.failed_count = failed
        job.processed_count = ordinal - failed
        if failed:
            _fail(
                session,
                job,
                "One or more required website pages failed. The previous ready index remains current.",
            )
            session.commit()
            return
        website_ingestion.require_artifacts(memberships)
        if job.source_snapshot_id is not None and not job.snapshot.get("reuse_stored"):
            source_snapshots.mark_ready(session, job.source_snapshot_id, memberships)
        processing_ids = list(
            dict.fromkeys(revision.processing_run_id for _, _, revision in memberships)
        )
        index = indexes.create_index_from_processing_runs(
            session,
            job.project_id,
            job.knowledge_set_id,
            processing_ids,
            ingestion_run_id=job.id,
            source_snapshot_id=job.source_snapshot_id,
            commit=False,
        )
        session.execute(
            insert(IndexSourceRevision),
            [
                {
                    "index_id": index.id,
                    "source_revision_id": revision.id,
                    "source_item_id": item.id,
                    "source_node_id": source_node_id,
                    "project_id": job.project_id,
                }
                for source_node_id, item, revision in memberships
            ],
        )
        job.stage = "indexing"
        job.chunk_count = index.chunk_count
        job.progress = 40
        job.status = "queued"
        job.execution_token = None
        job.failures = 0
        job.dispatched_at = None
        job.updated_at = now()
        session.commit()


def _finish_remote(session, job, index):
    items = session.scalars(
        select(WebsiteRunItem).where(WebsiteRunItem.run_id == job.id)
    ).all()
    for item in items:
        item.status = "succeeded"
        item.updated_at = now()
    job.status = "succeeded"
    job.stage = "complete"
    job.progress = 100
    job.processed_count = job.discovered_count
    job.failed_count = 0
    job.chunk_count = index.chunk_count
    job.embedded_count = index.embedded_count
    job.published_count = 1
    job.execution_token = None
    job.failures = 0
    job.error = None
    job.updated_at = job.finished_at = now()


def process_ingestion(run_id: UUID, db_engine=engine, connector_factory=None):
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid4()
    with Session(db_engine) as session:
        job = session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
        )
        if job is None or job.status != "queued" or job.failures >= 3:
            return
        job.status = "running"
        job.attempts += 1
        job.execution_token = token
        job.started_at = job.started_at or now()
        job.updated_at = now()
        job.error = None
        source_kind = job.snapshot.get("source_kind", "existing_files")
        session.commit()
    try:
        if source_kind in ("website", "s3", "notion", "confluence"):
            with Session(db_engine) as session:
                index = session.scalar(
                    select(IndexVersion).where(IndexVersion.ingestion_run_id == run_id)
                )
            if index is None:
                if source_kind == "website":
                    _advance_website(run_id, token, db_engine, connector_factory)
                elif source_kind == "s3":
                    _advance_s3(run_id, token, db_engine, connector_factory)
                elif source_kind == "notion":
                    _advance_notion(run_id, token, db_engine, connector_factory)
                else:
                    _advance_confluence(run_id, token, db_engine, connector_factory)
                return
            with Session(db_engine) as session:
                job = session.scalar(
                    select(IngestionRun)
                    .where(IngestionRun.id == run_id)
                    .with_for_update()
                )
                if job.status != "running" or job.execution_token != token:
                    return
                index = session.get(IndexVersion, index.id)
                job.stage = "indexing"
                job.chunk_count = index.chunk_count
                job.embedded_count = index.embedded_count
                if index.status in ("queued", "running"):
                    job.progress = 40 + int(
                        59 * index.embedded_count / index.chunk_count
                    )
                    job.status = "queued"
                    job.execution_token = None
                    job.failures = 0
                    job.dispatched_at = None
                    job.updated_at = now()
                    session.commit()
                    return
                if index.status != "succeeded":
                    _fail(
                        session,
                        job,
                        index.error or "The source index could not publish.",
                    )
                    session.commit()
                    return
                _finish_remote(session, job, index)
                session.commit()
                return
        with Session(db_engine) as session:
            job = session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return
            items = session.scalars(
                select(IngestionRunItem)
                .where(IngestionRunItem.run_id == run_id)
                .order_by(IngestionRunItem.document_id)
            ).all()
            failed = []
            waiting = []
            for item in items:
                processing = session.get(ProcessingRun, item.processing_run_id)
                if processing.status == "succeeded":
                    item.status = "ready"
                    item.chunk_count = processing.chunk_count
                    item.error = None
                elif processing.status in ("failed", "cancelled"):
                    item.status = "failed"
                    item.error = (
                        processing.error or "Document processing did not complete."
                    )
                    failed.append(item)
                else:
                    item.status = "processing"
                    waiting.append(item)
                item.updated_at = now()
            job.processed_count = sum(item.status == "ready" for item in items)
            job.failed_count = len(failed)
            job.chunk_count = sum(
                item.chunk_count for item in items if item.status == "ready"
            )
            if failed:
                _fail(
                    session,
                    job,
                    "One or more selected files could not be processed. Inspect run items and retry with a new run.",
                )
                _cancel_unpublished_work(session, run_id)
                session.commit()
                return
            if waiting:
                job.stage = "processing"
                job.progress = int(40 * job.processed_count / job.discovered_count)
                job.status = "queued"
                job.execution_token = None
                job.failures = 0
                job.dispatched_at = None
                job.updated_at = now()
                session.commit()
                return

            index = session.scalar(
                select(IndexVersion).where(IndexVersion.ingestion_run_id == run_id)
            )
            if index is None:
                indexes.create_index_from_processing_runs(
                    session,
                    job.project_id,
                    job.knowledge_set_id,
                    [item.processing_run_id for item in items],
                    ingestion_run_id=job.id,
                    commit=False,
                )
                job.stage = "indexing"
                job.progress = 40
                job.status = "queued"
                job.execution_token = None
                job.failures = 0
                job.dispatched_at = None
                job.updated_at = now()
                session.commit()
                return
            job.stage = "indexing"
            job.chunk_count = index.chunk_count
            job.embedded_count = index.embedded_count
            if index.status in ("queued", "running"):
                job.progress = 40 + int(59 * index.embedded_count / index.chunk_count)
                job.status = "queued"
                job.execution_token = None
                job.failures = 0
                job.dispatched_at = None
                job.updated_at = now()
                session.commit()
                return
            if index.status != "succeeded":
                _fail(
                    session,
                    job,
                    index.error or "The immutable index could not be published.",
                )
                session.commit()
                return
            for item in items:
                item.status = "succeeded"
                item.updated_at = now()
            job.status = "succeeded"
            job.stage = "complete"
            job.progress = 100
            job.processed_count = job.discovered_count
            job.failed_count = 0
            job.chunk_count = index.chunk_count
            job.embedded_count = index.embedded_count
            job.published_count = 1
            job.execution_token = None
            job.failures = 0
            job.error = None
            job.updated_at = job.finished_at = now()
            session.commit()
    except Exception as exc:
        transient = isinstance(exc, SQLAlchemyError) or (
            isinstance(exc, ConnectorFailure) and exc.issue.retryable
        )
        message = (
            exc.issue.message
            if isinstance(exc, ConnectorFailure)
            else (
                str(exc)
                if isinstance(exc, ProcessingError)
                else (
                    exc.detail
                    if isinstance(exc, HTTPException) and isinstance(exc.detail, str)
                    else "Ingestion coordination was interrupted. The run will retry from its saved checkpoint."
                )
            )
        )
        with Session(db_engine) as session:
            job = session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            if job is None or job.status != "running" or job.execution_token != token:
                return
            job.failures += 1
            if transient and job.failures < 3:
                job.status = "queued"
                job.execution_token = None
                job.error = message
                job.updated_at = job.dispatched_at = now()
            else:
                _fail(session, job, message)
                _cancel_unpublished_work(session, run_id)
            session.commit()


@celery.task(name="ingestion.coordinate", soft_time_limit=3660, time_limit=3670)
def coordinate_ingestion(run_id: str):
    process_ingestion(UUID(run_id))
