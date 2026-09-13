"""Project-scoped durable ingestion schedule operations."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.ingestion import IngestionRun, IngestionSchedule
from app.models.pipeline import Pipeline, PipelineVersion
from app.schemas.schedule import Cadence, ScheduleCreate, ScheduleUpdate
from app.services import ingestion
from app.services.documents import project
from app.workers.processing import now


def next_due(cadence: Cadence, after: datetime) -> datetime:
    after = after.astimezone(UTC)
    if cadence.kind == "interval":
        return after + timedelta(minutes=cadence.minutes)
    zone = ZoneInfo(cadence.timezone)
    local = after.astimezone(zone)
    candidate = datetime.combine(local.date(), cadence.local_time, tzinfo=zone)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def version(session, project_id, pipeline_id, version_id):
    row = session.scalar(
        select(PipelineVersion)
        .join(Pipeline, Pipeline.id == PipelineVersion.pipeline_id)
        .where(
            PipelineVersion.id == version_id,
            PipelineVersion.pipeline_id == pipeline_id,
            PipelineVersion.project_id == project_id,
            Pipeline.kind == "ingestion",
        )
    )
    if row is None:
        raise HTTPException(
            404, "Ingestion pipeline version not found in this project."
        )
    return row


def serialize(session, schedule):
    version = session.get(PipelineVersion, schedule.pipeline_version_id)
    return {
        "id": schedule.id,
        "project_id": schedule.project_id,
        "pipeline_id": version.pipeline_id,
        "pipeline_version_id": version.id,
        "pipeline_version": version.version,
        "name": schedule.name,
        "status": schedule.status,
        "cadence": schedule.cadence,
        "next_run_at": schedule.next_run_at,
        "last_run_id": schedule.last_run_id,
        "last_triggered_at": schedule.last_triggered_at,
        "last_outcome": schedule.last_outcome,
        "last_error": schedule.last_error,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


def get(session, project_id, schedule_id, *, lock=False):
    statement = select(IngestionSchedule).where(
        IngestionSchedule.id == schedule_id,
        IngestionSchedule.project_id == project_id,
    )
    if lock:
        statement = statement.with_for_update()
    row = session.scalar(statement)
    if row is None:
        raise HTTPException(404, "Ingestion schedule not found in this project.")
    return row


def create(session, project_id, data: ScheduleCreate):
    project(session, project_id)
    version(session, project_id, data.pipeline_id, data.pipeline_version_id)
    current = now()
    row = IngestionSchedule(
        project_id=project_id,
        pipeline_version_id=data.pipeline_version_id,
        name=data.name.strip(),
        status="enabled" if data.enabled else "paused",
        cadence=data.cadence.model_dump(mode="json"),
        next_run_at=next_due(data.cadence, current) if data.enabled else None,
        updated_at=current,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "A schedule with this name already exists.") from None
    session.refresh(row)
    return serialize(session, row)


def update(session, project_id, schedule_id, data: ScheduleUpdate):
    row = get(session, project_id, schedule_id, lock=True)
    current = now()
    row.name = data.name.strip()
    row.cadence = data.cadence.model_dump(mode="json")
    row.status = "enabled" if data.enabled else "paused"
    row.next_run_at = next_due(data.cadence, current) if data.enabled else None
    row.claim_token = row.claimed_at = None
    row.updated_at = current
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "A schedule with this name already exists.") from None
    session.refresh(row)
    return serialize(session, row)


def list_schedules(session, project_id, limit, offset):
    project(session, project_id)
    query = select(IngestionSchedule).where(IngestionSchedule.project_id == project_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(IngestionSchedule.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [serialize(session, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def trigger(session, project_id, schedule_id):
    row = get(session, project_id, schedule_id, lock=True)
    version = session.get(PipelineVersion, row.pipeline_version_id)
    current = now()
    result = ingestion.start_run(
        session,
        project_id,
        version.pipeline_id,
        version.id,
        trigger_kind="scheduled",
        schedule_id=row.id,
    )
    row = get(session, project_id, schedule_id, lock=True)
    row.last_run_id = result["id"]
    row.last_triggered_at = current
    row.last_outcome = "queued"
    row.last_error = None
    row.updated_at = current
    session.commit()
    return result


def refresh_outcome(session, row):
    if row.last_run_id is None:
        return
    run = session.get(IngestionRun, row.last_run_id)
    if run is not None and run.status != row.last_outcome:
        row.last_outcome = run.status
        row.last_error = run.error if run.status in ("failed", "cancelled") else None
        row.updated_at = now()
