"""Atomic local admission, idempotency and conservative budget reservation."""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import exists, func, select, text

from app.core.config import settings
from app.models.deployment import (
    AnswerDeployment,
    AnswerDeploymentRelease,
    DeployedAnswerRun,
    DeploymentUsageBucket,
    DeploymentUsageEntry,
)
from app.schemas.pipeline import Execution
from app.services import deployment_pricing
from app.services.deployments import _validated_release


def _deny(status, code):
    raise HTTPException(status, code)


def _count(session, *conditions):
    return session.scalar(
        select(func.count()).select_from(DeployedAnswerRun).where(*conditions)
    )


def _bucket(session, org, period, start):
    row = session.scalar(
        select(DeploymentUsageBucket)
        .where(
            DeploymentUsageBucket.organization_id == org,
            DeploymentUsageBucket.period == period,
            DeploymentUsageBucket.period_start == start,
        )
        .with_for_update()
    )
    if row is None:
        row = DeploymentUsageBucket(
            organization_id=org,
            period=period,
            period_start=start,
            accepted_count=0,
            reserved_usd=0,
            settled_usd=0,
        )
        session.add(row)
        session.flush()
    return row


def _deployment_reserved(session, deployment_id, since):
    released = exists(
        select(DeploymentUsageEntry.id).where(
            DeploymentUsageEntry.run_id == DeployedAnswerRun.id,
            DeploymentUsageEntry.entry_type == "release",
        )
    )
    return session.scalar(
        select(
            func.coalesce(func.sum(DeployedAnswerRun.cost_reservation_usd), 0)
        ).where(
            DeployedAnswerRun.deployment_id == deployment_id,
            DeployedAnswerRun.created_at >= since,
            ~released,
        )
    )


def admit(
    session, deployment: AnswerDeployment, key, question: str, idempotency_key: str
):
    if not idempotency_key:
        _deny(428, "idempotency_required")
    if len(idempotency_key) > 200 or any(
        ord(ch) < 33 or ord(ch) > 126 for ch in idempotency_key
    ):
        _deny(422, "invalid_idempotency_key")
    # One global transactional lock keeps org, deployment, key and queue counts
    # authoritative across API processes. The customer session uses READ COMMITTED.
    session.execute(text("SELECT pg_advisory_xact_lock(745199391)"))
    deployment = session.scalar(
        select(AnswerDeployment)
        .where(AnswerDeployment.id == deployment.id)
        .with_for_update()
    )
    request_hash = hashlib.sha256(question.encode()).hexdigest()
    existing = session.scalar(
        select(DeployedAnswerRun).where(
            DeployedAnswerRun.deployment_id == deployment.id,
            DeployedAnswerRun.client_id == key.client_id,
            DeployedAnswerRun.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            _deny(409, "idempotency_conflict")
        if existing.redacted_at is not None:
            _deny(410, "result_expired")
        return existing, True
    if deployment.state != "active" or deployment.active_release_id is None:
        _deny(409, "deployment_not_active")
    release = session.get(AnswerDeploymentRelease, deployment.active_release_id)
    if release is None:
        _deny(503, "release_unavailable")
    try:
        _validated_release(
            session, deployment, release.pipeline_version_id, release.index_id
        )
    except Exception:
        _deny(503, "release_unavailable")
    execution = Execution.model_validate(release.execution)
    reservation = deployment_pricing.worst_case(
        execution, release.embedding_config, len(question.encode("utf-8"))
    )
    now = datetime.now(timezone.utc)
    minute = now.replace(second=0, microsecond=0)
    since = minute
    if (
        _count(
            session,
            DeployedAnswerRun.client_id == key.client_id,
            DeployedAnswerRun.deployment_id == deployment.id,
            DeployedAnswerRun.created_at >= since,
        )
        >= settings.deployment_key_rpm
    ):
        _deny(429, "rate_limited")
    if _count(
        session,
        DeployedAnswerRun.deployment_id == deployment.id,
        DeployedAnswerRun.created_at >= since,
    ) >= min(settings.deployment_rpm, deployment.rate_per_minute):
        _deny(429, "rate_limited")
    if (
        _count(
            session,
            DeployedAnswerRun.organization_id == deployment.organization_id,
            DeployedAnswerRun.created_at >= since,
        )
        >= settings.deployment_org_rpm
    ):
        _deny(429, "rate_limited")
    queued = DeployedAnswerRun.status == "queued"
    if _count(session, queued, DeployedAnswerRun.deployment_id == deployment.id) >= min(
        settings.deployment_queue_cap, deployment.queued_runs
    ):
        _deny(429, "queue_full")
    if (
        _count(
            session,
            queued,
            DeployedAnswerRun.organization_id == deployment.organization_id,
        )
        >= settings.deployment_org_queue_cap
    ):
        _deny(429, "queue_full")
    if _count(session, queued) >= settings.deployment_global_queue_cap:
        _deny(429, "queue_full")
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    daily = _bucket(session, deployment.organization_id, "day", day)
    monthly = _bucket(session, deployment.organization_id, "month", month)
    if _deployment_reserved(session, deployment.id, day) + reservation > min(
        settings.deployment_org_daily_usd, deployment.daily_budget_usd
    ) or _deployment_reserved(session, deployment.id, month) + reservation > min(
        settings.deployment_org_monthly_usd, deployment.monthly_budget_usd
    ):
        _deny(402, "budget_exhausted")
    if (
        daily.reserved_usd + daily.settled_usd + reservation
        > settings.deployment_org_daily_usd
    ):
        _deny(402, "budget_exhausted")
    if (
        monthly.reserved_usd + monthly.settled_usd + reservation
        > settings.deployment_org_monthly_usd
    ):
        _deny(402, "budget_exhausted")
    run = DeployedAnswerRun(
        organization_id=deployment.organization_id,
        project_id=deployment.project_id,
        deployment_id=deployment.id,
        release_id=release.id,
        key_id=key.id,
        client_id=key.client_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        question=question,
        status="queued",
        stage="admitted",
        cost_reservation_usd=reservation,
        cost_basis_version=settings.deployment_pricing_version,
        attempts=0,
        result_expires_at=now
        + timedelta(days=settings.deployment_result_retention_days),
    )
    session.add(run)
    session.flush()
    for bucket in (daily, monthly):
        bucket.reserved_usd += reservation
        bucket.accepted_count += 1
        bucket.updated_at = now
    session.add(
        DeploymentUsageEntry(
            run_id=run.id,
            organization_id=deployment.organization_id,
            entry_type="reservation",
            amount_usd=reservation,
            basis=settings.deployment_pricing_version,
        )
    )
    session.commit()
    session.refresh(run)
    return run, False


def status(run):
    return {
        "id": run.id,
        "status": run.status,
        "stage": run.stage,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "retry_after_seconds": 2
        if run.status in {"queued", "running", "cancel_requested"}
        else None,
    }


def accepted(run, release):
    return {
        "id": run.id,
        "status": run.status,
        "release_number": release.release_number,
        "created_at": run.created_at,
        "status_url": f"/v1/answer-deployments/{run.deployment_id}/questions/{run.id}/status",
        "result_url": f"/v1/answer-deployments/{run.deployment_id}/questions/{run.id}/result",
    }
