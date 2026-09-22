"""Durable, worker-safe execution checkpoints for ingestion canvas nodes."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionRun, IngestionRunItem, IngestionRunNode


def now():
    return datetime.now(timezone.utc)


def _target(
    session: Session, run_id: UUID, *, node_id: str | None, node_type: str | None
):
    statement = select(IngestionRunNode).where(IngestionRunNode.run_id == run_id)
    if node_id is not None:
        statement = statement.where(IngestionRunNode.node_id == node_id)
    elif node_type is not None:
        statement = statement.where(IngestionRunNode.node_type == node_type)
    else:
        raise ValueError("A node id or node type is required.")
    return session.scalar(statement.order_by(IngestionRunNode.ordinal).limit(1))


def transition(
    db_engine,
    run_id: UUID,
    *,
    node_id: str | None = None,
    node_type: str | None = None,
    execution_token: UUID | None = None,
) -> bool:
    """Make one real node active and durably complete nodes before it."""
    with Session(db_engine) as session:
        run = session.get(IngestionRun, run_id)
        if run is None or run.status not in ("queued", "running"):
            return False
        if execution_token is not None and run.execution_token != execution_token:
            return False
        target = _target(session, run_id, node_id=node_id, node_type=node_type)
        if target is None:
            return False
        furthest_ordinal = session.scalar(
            select(IngestionRunNode.ordinal)
            .where(
                IngestionRunNode.run_id == run_id,
                IngestionRunNode.status.in_(["running", "succeeded"]),
            )
            .order_by(IngestionRunNode.ordinal.desc())
            .limit(1)
        )
        if target.status == "succeeded" or (
            furthest_ordinal is not None and target.ordinal < furthest_ordinal
        ):
            return True
        timestamp = now()
        session.execute(
            update(IngestionRunNode)
            .where(
                IngestionRunNode.run_id == run_id,
                IngestionRunNode.ordinal < target.ordinal,
                IngestionRunNode.status.in_(["queued", "running"]),
            )
            .values(status="succeeded", finished_at=timestamp, updated_at=timestamp)
        )
        if target.status not in ("failed", "cancelled"):
            target.status = "running"
            target.started_at = target.started_at or timestamp
            target.finished_at = None
            target.updated_at = timestamp
        session.commit()
        return True


def transition_for_processing_run(db_engine, processing_run_id: UUID, node_type: str):
    with Session(db_engine) as session:
        run_id = session.scalar(
            select(IngestionRunItem.run_id)
            .join(IngestionRun, IngestionRun.id == IngestionRunItem.run_id)
            .where(
                IngestionRunItem.processing_run_id == processing_run_id,
                IngestionRun.status.in_(["queued", "running"]),
            )
            .limit(1)
        )
    if run_id is not None:
        transition(db_engine, run_id, node_type=node_type)


def transition_for_index(db_engine, index, node_type: str):
    if index.ingestion_run_id is not None:
        transition(db_engine, index.ingestion_run_id, node_type=node_type)


def mark_terminal(session: Session, run_id: UUID, status: str):
    timestamp = now()
    if status == "succeeded":
        session.execute(
            update(IngestionRunNode)
            .where(
                IngestionRunNode.run_id == run_id,
                IngestionRunNode.status != "succeeded",
            )
            .values(status="succeeded", finished_at=timestamp, updated_at=timestamp)
        )
        return
    if status == "cancelled":
        session.execute(
            update(IngestionRunNode)
            .where(
                IngestionRunNode.run_id == run_id,
                IngestionRunNode.status != "succeeded",
            )
            .values(status="cancelled", finished_at=timestamp, updated_at=timestamp)
        )
        return
    active = session.scalar(
        select(IngestionRunNode)
        .where(
            IngestionRunNode.run_id == run_id,
            IngestionRunNode.status == "running",
        )
        .order_by(IngestionRunNode.ordinal.desc())
        .limit(1)
    )
    if active is None:
        active = session.scalar(
            select(IngestionRunNode)
            .where(
                IngestionRunNode.run_id == run_id,
                IngestionRunNode.status == "queued",
            )
            .order_by(IngestionRunNode.ordinal)
            .limit(1)
        )
    if active is not None:
        active.status = "failed"
        active.finished_at = timestamp
        active.updated_at = timestamp
