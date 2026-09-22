import hashlib
import json
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.project import Project
from app.models.source import (
    SourceItem,
    SourceRevision,
    SourceSnapshot,
    SourceSnapshotMember,
    WebsiteRunItem,
)
from app.schemas.ingestion import IngestionExecution
from app.services.documents import project
from app.workers.processing import now


def _source_configuration(execution: IngestionExecution) -> list[dict]:
    return [
        {"id": node.id, "config": node.config.model_dump(mode="json")}
        for node in execution.nodes
        if node.type == "source" and node.config.kind == "website"
    ]


def _configuration_hash(configuration: list[dict]) -> str:
    encoded = json.dumps(
        configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_origin(value: str) -> str:
    parsed = urlsplit(value)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _source_identity(configuration: list[dict]) -> dict:
    origins: set[str] = set()
    modes: list[str] = []
    for source in configuration:
        config = source["config"]
        selection = config.get("selection", {})
        modes.append(selection.get("mode", "unknown"))
        candidates = [
            selection.get("url"),
            selection.get("start_url"),
            selection.get("sitemap_url"),
            *selection.get("urls", []),
            *config.get("allowed_origins", []),
        ]
        for candidate in candidates:
            if candidate:
                origins.add(_safe_origin(candidate))
    return {"origins": sorted(origins), "selection_modes": sorted(set(modes))}


def create_collecting(
    session: Session,
    project_id: UUID,
    run: IngestionRun,
    execution: IngestionExecution,
) -> SourceSnapshot:
    configuration = _source_configuration(execution)
    config_hash = _configuration_hash(configuration)
    # Separate destinations may collect the same source concurrently, so allocate
    # the per-source display number while holding the project row lock.
    session.execute(
        select(Project.id).where(Project.id == project_id).with_for_update()
    )
    number = (
        session.scalar(
            select(func.max(SourceSnapshot.snapshot_number)).where(
                SourceSnapshot.project_id == project_id,
                SourceSnapshot.source_config_hash == config_hash,
            )
        )
        or 0
    ) + 1
    snapshot = SourceSnapshot(
        project_id=project_id,
        source_configuration=configuration,
        source_config_hash=config_hash,
        source_identity=_source_identity(configuration),
        connector_version="website-v1",
        snapshot_number=number,
        creating_ingestion_run_id=run.id,
    )
    session.add(snapshot)
    session.flush()
    run.source_snapshot_id = snapshot.id
    return snapshot


def mark_ready(
    session: Session,
    snapshot_id: UUID,
    memberships: list[tuple[str, SourceItem, SourceRevision]],
) -> SourceSnapshot:
    snapshot = session.scalar(
        select(SourceSnapshot).where(SourceSnapshot.id == snapshot_id).with_for_update()
    )
    if snapshot is None or snapshot.status != "collecting":
        raise HTTPException(409, "Source snapshot is not collecting.")
    run_items = session.scalars(
        select(WebsiteRunItem).where(
            WebsiteRunItem.run_id == snapshot.creating_ingestion_run_id
        )
    ).all()
    counts = {
        name: 0
        for name in (
            "new",
            "changed",
            "unchanged",
            "removed",
            "excluded",
            "duplicate",
            "failed",
        )
    }
    for item in run_items:
        counts[item.outcome] += 1
    values = []
    for ordinal, (source_node_id, item, revision) in enumerate(memberships):
        values.append(
            {
                "snapshot_id": snapshot.id,
                "ordinal": ordinal,
                "project_id": snapshot.project_id,
                "source_node_id": source_node_id,
                "source_item_id": item.id,
                "source_revision_id": revision.id,
                "inclusion_state": "included",
                "provenance": {
                    "canonical_location": item.canonical_location,
                    "provider_revision": revision.provider_revision,
                },
            }
        )
    if values:
        session.execute(insert(SourceSnapshotMember), values)
    snapshot.status = "ready"
    snapshot.discovered_count = len(run_items)
    snapshot.included_count = len(memberships)
    snapshot.excluded_count = counts["excluded"]
    snapshot.duplicate_count = counts["duplicate"]
    snapshot.failed_count = counts["failed"]
    snapshot.new_count = counts["new"]
    snapshot.changed_count = counts["changed"]
    snapshot.unchanged_count = counts["unchanged"]
    snapshot.removed_count = counts["removed"]
    snapshot.total_bytes = sum(revision.size_bytes for _, _, revision in memberships)
    snapshot.collected_at = now()
    snapshot.error = None
    return snapshot


def mark_terminal(session: Session, snapshot_id: UUID | None, status: str, error: str):
    if snapshot_id is None:
        return
    snapshot = session.scalar(
        select(SourceSnapshot).where(SourceSnapshot.id == snapshot_id).with_for_update()
    )
    if snapshot is not None and snapshot.status == "collecting":
        snapshot.status = status
        snapshot.error = error
        snapshot.collected_at = now()


def get(session: Session, project_id: UUID, snapshot_id: UUID) -> SourceSnapshot:
    snapshot = session.scalar(
        select(SourceSnapshot).where(
            SourceSnapshot.id == snapshot_id,
            SourceSnapshot.project_id == project_id,
        )
    )
    if snapshot is None:
        raise HTTPException(404, "Source snapshot not found in this project.")
    return snapshot


def require_compatible(
    session: Session,
    project_id: UUID,
    snapshot_id: UUID,
    execution: IngestionExecution,
) -> SourceSnapshot:
    snapshot = get(session, project_id, snapshot_id)
    if snapshot.status != "ready":
        raise HTTPException(409, "Only a ready source snapshot can build an index.")
    configuration = _source_configuration(execution)
    if _configuration_hash(configuration) != snapshot.source_config_hash:
        raise HTTPException(
            409,
            "This snapshot was collected with different Website source settings. "
            "Choose a compatible snapshot or collect the source again.",
        )
    return snapshot


def _snapshot_rows(session: Session, statement):
    index_count = (
        select(func.count())
        .select_from(IndexVersion)
        .where(IndexVersion.source_snapshot_id == SourceSnapshot.id)
        .correlate(SourceSnapshot)
        .scalar_subquery()
    )
    rows = session.execute(statement.add_columns(index_count)).all()
    return [
        {
            **{
                column.name: getattr(snapshot, column.name)
                for column in SourceSnapshot.__table__.columns
            },
            "downstream_index_count": downstream_count,
        }
        for snapshot, downstream_count in rows
    ]


def read(session: Session, project_id: UUID, snapshot_id: UUID):
    get(session, project_id, snapshot_id)
    return _snapshot_rows(
        session,
        select(SourceSnapshot).where(SourceSnapshot.id == snapshot_id),
    )[0]


def list_snapshots(session: Session, project_id: UUID, limit: int, offset: int):
    project(session, project_id)
    condition = SourceSnapshot.project_id == project_id
    total = session.scalar(
        select(func.count()).select_from(SourceSnapshot).where(condition)
    )
    items = _snapshot_rows(
        session,
        select(SourceSnapshot)
        .where(condition)
        .order_by(SourceSnapshot.created_at.desc(), SourceSnapshot.id.desc())
        .limit(limit)
        .offset(offset),
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def list_items(
    session: Session, project_id: UUID, snapshot_id: UUID, limit: int, offset: int
):
    get(session, project_id, snapshot_id)
    condition = (SourceSnapshotMember.snapshot_id == snapshot_id) & (
        SourceSnapshotMember.project_id == project_id
    )
    total = session.scalar(
        select(func.count()).select_from(SourceSnapshotMember).where(condition)
    )
    rows = session.execute(
        select(SourceSnapshotMember, SourceItem, SourceRevision)
        .join(SourceItem, SourceItem.id == SourceSnapshotMember.source_item_id)
        .join(
            SourceRevision, SourceRevision.id == SourceSnapshotMember.source_revision_id
        )
        .where(condition)
        .order_by(SourceSnapshotMember.ordinal)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                "ordinal": member.ordinal,
                "source_node_id": member.source_node_id,
                "source_item_id": item.id,
                "source_revision_id": revision.id,
                "inclusion_state": member.inclusion_state,
                "canonical_location": item.canonical_location,
                "media_type": revision.media_type,
                "size_bytes": revision.size_bytes,
                "fetched_at": revision.fetched_at,
                "provider_revision": revision.provider_revision,
                "provenance": member.provenance,
            }
            for member, item, revision in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def list_indexes(
    session: Session, project_id: UUID, snapshot_id: UUID, limit: int, offset: int
):
    get(session, project_id, snapshot_id)
    condition = (IndexVersion.source_snapshot_id == snapshot_id) & (
        IndexVersion.project_id == project_id
    )
    total = session.scalar(
        select(func.count()).select_from(IndexVersion).where(condition)
    )
    rows = session.execute(
        select(IndexVersion, KnowledgeSet, IngestionRun, PipelineVersion, Pipeline)
        .join(KnowledgeSet, KnowledgeSet.id == IndexVersion.knowledge_set_id)
        .outerjoin(IngestionRun, IngestionRun.id == IndexVersion.ingestion_run_id)
        .outerjoin(
            PipelineVersion, PipelineVersion.id == IngestionRun.pipeline_version_id
        )
        .outerjoin(Pipeline, Pipeline.id == PipelineVersion.pipeline_id)
        .where(condition)
        .order_by(IndexVersion.created_at.desc(), IndexVersion.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": index.id,
                "knowledge_set_id": knowledge_set.id,
                "knowledge_set_name": knowledge_set.name,
                "version": index.version,
                "status": index.status,
                "chunk_count": index.chunk_count,
                "embedded_count": index.embedded_count,
                "is_current": knowledge_set.current_ready_index_id == index.id,
                "ingestion_pipeline_id": pipeline.id if pipeline else None,
                "ingestion_pipeline_name": pipeline.name if pipeline else None,
                "ingestion_pipeline_version": version.version if version else None,
                "created_at": index.created_at,
            }
            for index, knowledge_set, _run, version, pipeline in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
