"""Durable, worker-safe execution checkpoints for ingestion canvas nodes."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionRun, IngestionRunItem, IngestionRunNode


def now():
    return datetime.now(timezone.utc)


def transition(
    db_engine,
    run_id: UUID,
    *,
    node_id: str | None = None,
    node_type: str | None = None,
    execution_token: UUID | None = None,
) -> bool:
    """Make one real node active and durably complete nodes before it."""
    if node_id is None and node_type is None:
        raise ValueError("A node id or node type is required.")
    worker_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    with Session(worker_engine) as session:
        # One ingestion run can have several document workers. Lock its ordered node
        # set so their shared Extract/Clean/Chunk checkpoints cannot move backwards or
        # fail a repeatable-read transaction with a concurrent-update serialization.
        nodes = session.scalars(
            select(IngestionRunNode)
            .where(IngestionRunNode.run_id == run_id)
            .order_by(IngestionRunNode.ordinal)
            .with_for_update()
        ).all()
        run = session.get(IngestionRun, run_id)
        if run is None or run.status not in ("queued", "running"):
            return False
        if execution_token is not None and run.execution_token != execution_token:
            return False
        target = next(
            (
                node
                for node in nodes
                if (node_id is not None and node.node_id == node_id)
                or (node_id is None and node.node_type == node_type)
            ),
            None,
        )
        if target is None:
            return False
        furthest_ordinal = max(
            (node.ordinal for node in nodes if node.status in ("running", "succeeded")),
            default=None,
        )
        if target.status == "succeeded" or (
            furthest_ordinal is not None and target.ordinal < furthest_ordinal
        ):
            return True
        timestamp = now()
        for node in nodes:
            if node.ordinal >= target.ordinal:
                break
            if node.status in ("queued", "running"):
                node.status = "succeeded"
                node.finished_at = timestamp
                node.updated_at = timestamp
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
