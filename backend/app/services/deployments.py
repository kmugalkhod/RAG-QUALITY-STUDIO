"""Release lifecycle; all writes commit an event with their state change."""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.deployment import (
    AnswerDeployment,
    AnswerDeploymentEvent,
    AnswerDeploymentRelease,
    AnswerDeploymentKey,
    DeployedAnswerRun,
)
from app.models.index import IndexVersion
from app.models.pipeline import Pipeline
from app.models.project import Project
from app.core.config import settings
from app.providers import embeddings, generation
from app.schemas.pipeline import Execution
from app.services import pipelines
from app.services.deployment_commands import record


def _hash(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _state_response(row):
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "project_id": row.project_id,
        "pipeline_id": row.pipeline_id,
        "name": row.name,
        "state": row.state,
        "active_release_id": row.active_release_id,
        "revision": row.revision,
        "accepting_questions": row.state == "active",
        "created_at": row.created_at,
        "limits": {
            "rate_per_minute": row.rate_per_minute,
            "concurrent_runs": row.concurrent_runs,
            "queued_runs": row.queued_runs,
            "daily_budget_usd": row.daily_budget_usd,
            "monthly_budget_usd": row.monthly_budget_usd,
        },
    }


def _event(session, deployment, event_type, actor, *, old=None, new=None, reason=""):
    session.add(
        AnswerDeploymentEvent(
            deployment_id=deployment.id,
            organization_id=deployment.organization_id,
            project_id=deployment.project_id,
            event_type=event_type,
            actor_kind="user",
            actor_id=actor,
            old_release_id=old,
            new_release_id=new,
            reason=reason,
        )
    )


def project_owner(session, project_id, principal, role):
    project = session.get(Project, project_id)
    if project is None or not project.organization_id:
        raise HTTPException(404, "Project not found.")
    if (
        principal.auth_mode == "clerk"
        and project.organization_id != principal.organization_id
    ):
        raise HTTPException(404, "Project not found.")
    if role not in {"owner", "admin"}:
        raise HTTPException(403, "Owner or admin access is required.")
    return project


def get_deployment(session, project_id, deployment_id, organization_id, *, lock=False):
    query = select(AnswerDeployment).where(
        AnswerDeployment.id == deployment_id,
        AnswerDeployment.project_id == project_id,
        AnswerDeployment.organization_id == organization_id,
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise HTTPException(404, "Answer deployment not found.")
    return row


def list_deployments(session, project_id, organization_id, limit, offset):
    query = select(AnswerDeployment).where(
        AnswerDeployment.project_id == project_id,
        AnswerDeployment.organization_id == organization_id,
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(AnswerDeployment.created_at.desc(), AnswerDeployment.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def _validated_release(session, deployment, version_id, index_id):
    pipeline = session.scalar(
        select(Pipeline).where(
            Pipeline.id == deployment.pipeline_id,
            Pipeline.project_id == deployment.project_id,
            Pipeline.kind == "answer",
        )
    )
    if pipeline is None:
        raise HTTPException(409, "The saved answer pipeline is unavailable.")
    version = pipelines.get_version(
        session, deployment.project_id, deployment.pipeline_id, version_id
    )
    execution = Execution.model_validate(version.execution)
    retriever = next(n for n in execution.nodes if n.type == "retriever")
    if retriever.index_id != index_id:
        raise HTTPException(
            409, "The saved retriever index differs from the requested index."
        )
    index = session.scalar(
        select(IndexVersion).where(
            IndexVersion.id == index_id,
            IndexVersion.project_id == deployment.project_id,
        )
    )
    if (
        index is None
        or index.status != "succeeded"
        or index.embedded_count != index.chunk_count
    ):
        raise HTTPException(409, "The selected index is not ready.")
    llm = next(n for n in execution.nodes if n.type == "llm")
    try:
        generation.configured(llm.model, llm.max_tokens, llm.temperature)
        current_embedding = embeddings.configured()
    except (generation.GenerationError, embeddings.EmbeddingError):
        raise HTTPException(503, "The saved release provider is unavailable.") from None
    if (
        embeddings.EmbeddingConfig.model_validate(index.embedding_config)
        != current_embedding
    ):
        raise HTTPException(409, "The index embedding configuration is unavailable.")
    return version, index, execution


def _new_release(session, deployment, version_id, index_id, note, actor, number):
    version, index, execution = _validated_release(
        session, deployment, version_id, index_id
    )
    data = execution.model_dump(mode="json")
    row = AnswerDeploymentRelease(
        deployment_id=deployment.id,
        organization_id=deployment.organization_id,
        project_id=deployment.project_id,
        pipeline_id=deployment.pipeline_id,
        pipeline_version_id=version.id,
        index_id=index.id,
        release_number=number,
        execution=data,
        execution_sha256=_hash(data),
        embedding_config=index.embedding_config,
        embedding_sha256=_hash(index.embedding_config),
        schema_version=execution.schema_version,
        runtime_contract_version=1,
        created_by=actor,
        note=note,
    )
    session.add(row)
    session.flush()
    return row


def create(session, project, payload, actor, *, command=None):
    deployment = AnswerDeployment(
        organization_id=project.organization_id,
        project_id=project.id,
        pipeline_id=payload.pipeline_id,
        name=payload.name,
        created_by=actor,
        rate_per_minute=settings.deployment_rpm,
        concurrent_runs=settings.deployment_concurrency,
        queued_runs=settings.deployment_queue_cap,
        daily_budget_usd=settings.deployment_org_daily_usd,
        monthly_budget_usd=settings.deployment_org_monthly_usd,
    )
    session.add(deployment)
    session.flush()
    release = _new_release(
        session,
        deployment,
        payload.pipeline_version_id,
        payload.index_id,
        payload.note,
        actor,
        1,
    )
    _event(session, deployment, "created", actor, new=release.id)
    record(session, command, deployment.id, {"release_id": release.id})
    session.commit()
    session.refresh(deployment)
    return deployment, release


def stage(session, deployment, payload, actor, *, command=None):
    if deployment.state == "archived":
        raise HTTPException(409, "Archived deployments cannot be changed.")
    next_number = session.scalar(
        select(
            func.coalesce(func.max(AnswerDeploymentRelease.release_number), 0) + 1
        ).where(AnswerDeploymentRelease.deployment_id == deployment.id)
    )
    release = _new_release(
        session,
        deployment,
        payload.pipeline_version_id,
        payload.index_id,
        payload.note,
        actor,
        next_number,
    )
    deployment.revision += 1
    deployment.updated_at = datetime.now(timezone.utc)
    _event(session, deployment, "release_created", actor, new=release.id)
    record(session, command, release.id, {})
    session.commit()
    return release


def revision_matches(deployment, expected):
    if expected != deployment.revision:
        raise HTTPException(412, "The deployment changed. Refresh and retry.")


def transition(
    session,
    deployment,
    action,
    actor,
    expected,
    *,
    release_id=None,
    reason="",
    command=None,
):
    revision_matches(deployment, expected)
    if deployment.state == "archived":
        raise HTTPException(409, "Archived deployments cannot be changed.")
    old = deployment.active_release_id
    if action == "promote":
        release = session.scalar(
            select(AnswerDeploymentRelease).where(
                AnswerDeploymentRelease.id == release_id,
                AnswerDeploymentRelease.deployment_id == deployment.id,
            )
        )
        if release is None:
            raise HTTPException(404, "Release not found.")
        _validated_release(
            session, deployment, release.pipeline_version_id, release.index_id
        )
        from app.services.deployment_pricing import worst_case

        worst_case(
            Execution.model_validate(release.execution), release.embedding_config, 32000
        )
        if old == release.id and deployment.state == "active":
            record(session, command, deployment.id, _state_response(deployment))
            session.commit()
            return deployment
        deployment.active_release_id = release.id
        deployment.state = "active"
        event = (
            "rolled_back"
            if old
            and release.release_number
            < session.scalar(
                select(AnswerDeploymentRelease.release_number).where(
                    AnswerDeploymentRelease.id == old
                )
            )
            else "promoted"
        )
    elif action == "pause":
        if deployment.state == "paused":
            record(session, command, deployment.id, _state_response(deployment))
            session.commit()
            return deployment
        deployment.state = "paused"
        event = "paused"
    elif action == "resume":
        if old is None:
            raise HTTPException(409, "Promote a release before resuming.")
        release = session.get(AnswerDeploymentRelease, old)
        _validated_release(
            session, deployment, release.pipeline_version_id, release.index_id
        )
        from app.services.deployment_pricing import worst_case

        worst_case(
            Execution.model_validate(release.execution), release.embedding_config, 32000
        )
        deployment.state = "active"
        event = "resumed"
    elif action == "archive":
        from app.workers.deployed_answers import _release_reservation

        deployment.state = "archived"
        deployment.archived_at = datetime.now(timezone.utc)
        for key in session.scalars(
            select(AnswerDeploymentKey).where(
                AnswerDeploymentKey.deployment_id == deployment.id,
                AnswerDeploymentKey.revoked_at.is_(None),
            )
        ):
            key.revoked_at = deployment.archived_at
        for run in session.scalars(
            select(DeployedAnswerRun)
            .where(
                DeployedAnswerRun.deployment_id == deployment.id,
                DeployedAnswerRun.status.in_(["queued", "running"]),
            )
            .with_for_update()
        ):
            run.cancel_requested_at = deployment.archived_at
            if run.status == "queued":
                run.status = "cancelled"
                run.stage = "terminal"
                run.finished_at = deployment.archived_at
                _release_reservation(session, run)
            else:
                run.status = "cancel_requested"
        event = "archived"
    else:
        raise ValueError(action)
    deployment.revision += 1
    deployment.updated_at = datetime.now(timezone.utc)
    _event(
        session,
        deployment,
        event,
        actor,
        old=old,
        new=deployment.active_release_id,
        reason=reason,
    )
    record(session, command, deployment.id, _state_response(deployment))
    session.commit()
    session.refresh(deployment)
    return deployment


def releases(session, deployment, limit, offset):
    query = select(AnswerDeploymentRelease).where(
        AnswerDeploymentRelease.deployment_id == deployment.id
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(
            AnswerDeploymentRelease.release_number.desc(),
            AnswerDeploymentRelease.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": rows, "total": total, "limit": limit, "offset": offset}
