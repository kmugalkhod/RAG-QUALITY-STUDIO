"""Fenced execution of bounded source-preview jobs."""

from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure
from app.connectors.website import WebsiteConnector
from app.db.session import engine
from app.models.preview import SourcePreview, SourcePreviewItem
from app.schemas.ingestion import IngestionExecution
from app.services import ingestion
from app.workers.celery_app import celery
from app.workers.processing import now


def _outcomes(db_session, project_id, execution):
    results = []
    for source in [node for node in execution.nodes if node.type == "source"]:
        if source.config.kind == "existing_files":
            existing_execution = execution.model_copy(
                update={
                    "nodes": [
                        node
                        for node in execution.nodes
                        if node.type != "source" or node.id == source.id
                    ],
                    "edges": [
                        edge
                        for edge in execution.edges
                        if edge.source == source.id
                        or edge.source
                        not in {
                            node.id for node in execution.nodes if node.type == "source"
                        }
                    ],
                }
            )
            for item in ingestion.preview(
                db_session, project_id, existing_execution
            ).items:
                results.append(
                    dict(
                        source_node_id=source.id,
                        external_id=str(item.document_id),
                        display_name=item.filename,
                        canonical_location=f"project-file:{item.document_id}",
                        media_type=item.media_type,
                        status="included" if item.included else "excluded",
                        reason=item.reason,
                        size_bytes=item.size_bytes,
                        depth=None,
                        error_code=None,
                    )
                )
        else:
            for item in WebsiteConnector().discover_all(source.config):
                results.append(dict(source_node_id=source.id, **item.__dict__))
    return results


def process_preview(preview_id: UUID, db_engine=engine, connector_factory=None):
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid4()
    with Session(db_engine) as session:
        preview = session.scalar(
            select(SourcePreview)
            .where(SourcePreview.id == preview_id)
            .with_for_update()
        )
        if preview is None or preview.status != "queued" or preview.failures >= 3:
            return
        preview.status = "running"
        preview.progress = 5
        preview.attempts += 1
        preview.execution_token = token
        preview.started_at = preview.started_at or now()
        preview.updated_at = now()
        preview.error = None
        execution = IngestionExecution.model_validate(preview.execution)
        project_id = preview.project_id
        session.commit()
    try:
        with Session(db_engine) as session:
            if connector_factory is None:
                outcomes = _outcomes(session, project_id, execution)
            else:
                outcomes = connector_factory(session, project_id, execution)
        counts = {kind: 0 for kind in ("included", "excluded", "duplicate", "failed")}
        for item in outcomes:
            counts[item["status"]] += 1
        with Session(db_engine) as session:
            preview = session.scalar(
                select(SourcePreview)
                .where(SourcePreview.id == preview_id)
                .with_for_update()
            )
            if (
                preview is None
                or preview.status != "running"
                or preview.execution_token != token
            ):
                return
            session.execute(
                delete(SourcePreviewItem).where(
                    SourcePreviewItem.preview_id == preview.id
                )
            )
            for ordinal, item in enumerate(outcomes):
                session.add(
                    SourcePreviewItem(preview_id=preview.id, ordinal=ordinal, **item)
                )
            preview.status = "succeeded"
            preview.progress = 100
            preview.discovered_count = len(outcomes)
            preview.included_count = counts["included"]
            preview.excluded_count = counts["excluded"]
            preview.duplicate_count = counts["duplicate"]
            preview.failed_count = counts["failed"]
            preview.execution_token = None
            preview.failures = 0
            preview.error = None
            preview.updated_at = preview.finished_at = now()
            session.commit()
    except Exception as exc:
        retryable = isinstance(exc, SQLAlchemyError) or (
            isinstance(exc, ConnectorFailure) and exc.issue.retryable
        )
        safe_error = (
            exc.issue.message
            if isinstance(exc, ConnectorFailure)
            else "Source preview was interrupted. Retry from its durable job record."
        )
        with Session(db_engine) as session:
            preview = session.scalar(
                select(SourcePreview)
                .where(SourcePreview.id == preview_id)
                .with_for_update()
            )
            if (
                preview is None
                or preview.status != "running"
                or preview.execution_token != token
            ):
                return
            preview.failures += 1
            preview.execution_token = None
            preview.error = safe_error
            preview.updated_at = now()
            if retryable and preview.failures < 3:
                preview.status = "queued"
                preview.dispatched_at = None
            else:
                preview.status = "failed"
                preview.finished_at = now()
            session.commit()


@celery.task(name="preview.sources", soft_time_limit=3660, time_limit=3670)
def preview_sources(preview_id: str):
    process_preview(UUID(preview_id))
