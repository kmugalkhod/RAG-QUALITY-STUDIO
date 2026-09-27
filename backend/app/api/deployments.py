"""Clerk/project-authorized deployment management API."""

from typing import Annotated
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.session import get_deployment_session
from app.core.auth import CurrentPrincipal, project_role, require_project_access
from app.models.deployment import (
    AnswerDeploymentKey,
    AnswerDeploymentRelease,
    DeployedAnswerRun,
)
from app.models.project import Project
from app.schemas.deployment import (
    DeploymentCreate,
    KeyCreate,
    LimitsInput,
    PromotionInput,
    ReasonInput,
    ReleaseInput,
)
from app.core import deployment_auth
from app.core.config import settings
from app.services import deployments, deployment_commands

router = APIRouter(
    prefix="/api/projects/{project_id}/answer-deployments",
    dependencies=[Depends(require_project_access)],
)
ManagementDatabase = Annotated[Session, Depends(get_deployment_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _org(session, project_id, principal):
    project = session.get(Project, project_id)
    if project is None or not project.organization_id:
        raise HTTPException(404, "Project not found.")
    if (
        principal.auth_mode == "clerk"
        and project.organization_id != principal.organization_id
    ):
        raise HTTPException(404, "Project not found.")
    return project


def _owner(session, project_id, principal):
    project = _org(session, project_id, principal)
    deployments.project_owner(
        session, project_id, principal, project_role(session, project_id, principal)
    )
    return project


def _read(session, project_id, deployment_id, principal, lock=False):
    project = _org(session, project_id, principal)
    return deployments.get_deployment(
        session, project_id, deployment_id, project.organization_id, lock=lock
    )


def _etag(value: str | None) -> int:
    if (
        not value
        or len(value) > 12
        or not value.startswith('"')
        or not value.endswith('"')
    ):
        raise HTTPException(428, "A quoted If-Match revision is required.")
    try:
        return int(value[1:-1])
    except ValueError:
        raise HTTPException(
            422, "If-Match must contain the deployment revision."
        ) from None


def _deployment(row, session=None):
    accepting = row.state == "active"
    if accepting and session is not None:
        release = session.get(AnswerDeploymentRelease, row.active_release_id)
        try:
            if release is None:
                accepting = False
            else:
                deployments._validated_release(
                    session, row, release.pipeline_version_id, release.index_id
                )
        except Exception:
            accepting = False
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "project_id": row.project_id,
        "pipeline_id": row.pipeline_id,
        "name": row.name,
        "state": row.state,
        "active_release_id": row.active_release_id,
        "revision": row.revision,
        "accepting_questions": accepting,
        "created_at": row.created_at,
        "limits": _limits(row),
    }


def _limits(row):
    return {
        "rate_per_minute": row.rate_per_minute,
        "concurrent_runs": row.concurrent_runs,
        "queued_runs": row.queued_runs,
        "daily_budget_usd": row.daily_budget_usd,
        "monthly_budget_usd": row.monthly_budget_usd,
    }


def _release(row):
    return {
        "id": row.id,
        "release_number": row.release_number,
        "pipeline_version_id": row.pipeline_version_id,
        "index_id": row.index_id,
        "execution_sha256": row.execution_sha256,
        "embedding_sha256": row.embedding_sha256,
        "schema_version": row.schema_version,
        "runtime_contract_version": row.runtime_contract_version,
        "created_at": row.created_at,
        "note": row.note,
    }


@router.get("")
def listing(
    project_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    limit: Limit = 20,
    offset: Offset = 0,
):
    project = _org(session, project_id, principal)
    page = deployments.list_deployments(
        session, project_id, project.organization_id, limit, offset
    )
    return {**page, "items": [_deployment(row, session) for row in page["items"]]}


@router.get("/permissions")
def permissions(
    project_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
):
    _org(session, project_id, principal)
    role = project_role(session, project_id, principal)
    return {"role": role, "can_manage": role in {"owner", "admin"}}


@router.post("", status_code=201)
def create(
    project_id: UUID,
    payload: DeploymentCreate,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    project = _owner(session, project_id, principal)
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        None,
        "create",
        idempotency_key,
        payload.model_dump(mode="json"),
    )
    if replay is not None:
        row = _read(session, project_id, replay.resource_id, principal)
        release = session.get(AnswerDeploymentRelease, replay.response["release_id"])
        return {**_deployment(row), "releases": [_release(release)]}
    row, release = deployments.create(
        session, project, payload, principal.user_id, command=command
    )
    return {**_deployment(row), "releases": [_release(release)]}


@router.get("/{deployment_id}")
def detail(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
):
    return _deployment(_read(session, project_id, deployment_id, principal), session)


@router.get("/{deployment_id}/limits")
def get_limits(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
):
    return _limits(_read(session, project_id, deployment_id, principal))


@router.put("/{deployment_id}/limits")
def put_limits(
    project_id: UUID,
    deployment_id: UUID,
    payload: LimitsInput,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    if_match: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "limits",
        idempotency_key,
        {"limits": payload.model_dump(mode="json"), "revision": if_match},
    )
    if replay is not None:
        return replay.response
    deployments.revision_matches(row, _etag(if_match))
    if row.state == "archived":
        raise HTTPException(409, "Archived deployments cannot be changed.")
    ceilings = {
        "rate_per_minute": settings.deployment_rpm,
        "concurrent_runs": settings.deployment_concurrency,
        "queued_runs": settings.deployment_queue_cap,
        "daily_budget_usd": settings.deployment_org_daily_usd,
        "monthly_budget_usd": settings.deployment_org_monthly_usd,
    }
    values = payload.model_dump()
    if any(values[name] > ceiling for name, ceiling in ceilings.items()):
        raise HTTPException(422, "A deployment limit exceeds its operator ceiling.")
    for name, value in values.items():
        setattr(row, name, value)
    row.revision += 1
    row.updated_at = datetime.now(timezone.utc)
    deployments._event(session, row, "limit_changed", principal.user_id)
    deployment_commands.record(session, command, row.id, _deployment(row))
    session.commit()
    return _deployment(row)


@router.get("/{deployment_id}/events")
def events(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    limit: Limit = 20,
    offset: Offset = 0,
):
    row = _read(session, project_id, deployment_id, principal)
    from app.models.deployment import AnswerDeploymentEvent

    query = select(AnswerDeploymentEvent).where(
        AnswerDeploymentEvent.deployment_id == row.id
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(
        query.order_by(
            AnswerDeploymentEvent.created_at.desc(), AnswerDeploymentEvent.id.desc()
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "old_release_id": item.old_release_id,
                "new_release_id": item.new_release_id,
                "reason": item.reason,
                "created_at": item.created_at,
            }
            for item in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{deployment_id}/releases")
def release_list(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    limit: Limit = 20,
    offset: Offset = 0,
):
    row = _read(session, project_id, deployment_id, principal)
    page = deployments.releases(session, row, limit, offset)
    return {**page, "items": [_release(item) for item in page["items"]]}


@router.get("/{deployment_id}/releases/{release_id}")
def release_detail(
    project_id: UUID,
    deployment_id: UUID,
    release_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
):
    row = _read(session, project_id, deployment_id, principal)
    release = session.get(AnswerDeploymentRelease, release_id)
    if release is None or release.deployment_id != row.id:
        raise HTTPException(404, "Release not found.")
    return _release(release)


@router.post("/{deployment_id}/releases", status_code=201)
def stage(
    project_id: UUID,
    deployment_id: UUID,
    payload: ReleaseInput,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "stage",
        idempotency_key,
        payload.model_dump(mode="json"),
    )
    if replay is not None:
        release = session.get(AnswerDeploymentRelease, replay.resource_id)
        return _release(release)
    return _release(
        deployments.stage(session, row, payload, principal.user_id, command=command)
    )


@router.post("/{deployment_id}/promotions")
def promote(
    project_id: UUID,
    deployment_id: UUID,
    payload: PromotionInput,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    if_match: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "promote",
        idempotency_key,
        {"payload": payload.model_dump(mode="json"), "revision": if_match},
    )
    if replay is not None:
        return replay.response
    changed = deployments.transition(
        session,
        row,
        "promote",
        principal.user_id,
        _etag(if_match),
        release_id=payload.release_id,
        reason=payload.reason,
        command=command,
    )
    return _deployment(changed)


@router.post("/{deployment_id}/pause")
def pause(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    if_match: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "pause",
        idempotency_key,
        {"revision": if_match},
    )
    if replay is not None:
        return replay.response
    return _deployment(
        deployments.transition(
            session, row, "pause", principal.user_id, _etag(if_match), command=command
        )
    )


@router.post("/{deployment_id}/resume")
def resume(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    if_match: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "resume",
        idempotency_key,
        {"revision": if_match},
    )
    if replay is not None:
        return replay.response
    return _deployment(
        deployments.transition(
            session, row, "resume", principal.user_id, _etag(if_match), command=command
        )
    )


@router.post("/{deployment_id}/archive")
def archive(
    project_id: UUID,
    deployment_id: UUID,
    payload: ReasonInput,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    if_match: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "archive",
        idempotency_key,
        {"payload": payload.model_dump(mode="json"), "revision": if_match},
    )
    if replay is not None:
        return replay.response
    return _deployment(
        deployments.transition(
            session,
            row,
            "archive",
            principal.user_id,
            _etag(if_match),
            reason=payload.reason,
            command=command,
        )
    )


@router.get("/{deployment_id}/keys")
def key_list(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    response: Response,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal)
    response.headers["Cache-Control"] = "no-store"
    keys = session.scalars(
        select(AnswerDeploymentKey)
        .where(AnswerDeploymentKey.deployment_id == row.id)
        .order_by(AnswerDeploymentKey.created_at.desc(), AnswerDeploymentKey.id.desc())
    ).all()
    return {"items": [deployment_auth.metadata(key) for key in keys]}


@router.post("/{deployment_id}/keys", status_code=201)
def key_create(
    project_id: UUID,
    deployment_id: UUID,
    payload: KeyCreate,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    command, _ = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "key_create",
        idempotency_key,
        payload.model_dump(mode="json"),
    )
    key, secret = deployment_auth.create_key(
        session,
        row,
        payload.label,
        payload.expires_at,
        principal.user_id,
        command=command,
    )
    response.headers["Cache-Control"] = "no-store"
    return {**deployment_auth.metadata(key), "secret": secret}


@router.post("/{deployment_id}/keys/{key_id}/rotate", status_code=201)
def key_rotate(
    project_id: UUID,
    deployment_id: UUID,
    key_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    key = session.get(AnswerDeploymentKey, key_id)
    if key is None or key.deployment_id != row.id:
        raise HTTPException(404, "Deployment key not found.")
    command, _ = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "key_rotate",
        idempotency_key,
        {"key_id": str(key_id)},
    )
    replacement, secret = deployment_auth.rotate_key(
        session, row, key, principal.user_id, command=command
    )
    response.headers["Cache-Control"] = "no-store"
    return {**deployment_auth.metadata(replacement), "secret": secret}


@router.post("/{deployment_id}/keys/{key_id}/revoke")
def key_revoke(
    project_id: UUID,
    deployment_id: UUID,
    key_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    key = session.get(AnswerDeploymentKey, key_id)
    if key is None or key.deployment_id != row.id:
        raise HTTPException(404, "Deployment key not found.")
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "key_revoke",
        idempotency_key,
        {"key_id": str(key_id)},
    )
    if replay is not None:
        return replay.response
    response.headers["Cache-Control"] = "no-store"
    return deployment_auth.metadata(
        deployment_auth.revoke_key(
            session, row, key, principal.user_id, command=command
        )
    )


def _run_summary(run, include_result=False):
    summary = {
        "id": run.id,
        "release_id": run.release_id,
        "status": run.status,
        "stage": run.stage,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error_code": run.error_code,
        "cost_reservation_usd": run.cost_reservation_usd,
    }
    if include_result:
        summary.update(answer=run.answer, citations=run.citations)
    return summary


@router.get("/{deployment_id}/runs")
def run_list(
    project_id: UUID,
    deployment_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    limit: Limit = 20,
    offset: Offset = 0,
):
    row = _read(session, project_id, deployment_id, principal)
    query = select(DeployedAnswerRun).where(DeployedAnswerRun.deployment_id == row.id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(DeployedAnswerRun.created_at.desc(), DeployedAnswerRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [_run_summary(item) for item in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{deployment_id}/runs/{run_id}")
def run_detail(
    project_id: UUID,
    deployment_id: UUID,
    run_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
):
    row = _read(session, project_id, deployment_id, principal)
    run = session.scalar(
        select(DeployedAnswerRun).where(
            DeployedAnswerRun.id == run_id,
            DeployedAnswerRun.deployment_id == row.id,
        )
    )
    if run is None:
        raise HTTPException(404, "Run not found.")
    role = project_role(session, project_id, principal)
    return _run_summary(run, include_result=role in {"owner", "admin"})


@router.post("/{deployment_id}/runs/{run_id}/cancel")
def cancel_run(
    project_id: UUID,
    deployment_id: UUID,
    run_id: UUID,
    session: ManagementDatabase,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _owner(session, project_id, principal)
    row = _read(session, project_id, deployment_id, principal, lock=True)
    run = session.scalar(
        select(DeployedAnswerRun)
        .where(
            DeployedAnswerRun.id == run_id,
            DeployedAnswerRun.deployment_id == row.id,
        )
        .with_for_update()
    )
    if run is None:
        raise HTTPException(404, "Run not found.")
    command, replay = deployment_commands.prepare(
        session,
        principal.user_id,
        project_id,
        deployment_id,
        "cancel_run",
        idempotency_key,
        {"run_id": str(run_id)},
    )
    if replay is not None:
        return replay.response
    if run.status == "queued":
        from app.workers.deployed_answers import _release_reservation

        run.status = "cancelled"
        run.stage = "terminal"
        run.finished_at = datetime.now(timezone.utc)
        run.cancel_requested_at = run.finished_at
        _release_reservation(session, run)
    elif run.status == "running":
        run.status = "cancel_requested"
        run.cancel_requested_at = datetime.now(timezone.utc)
    deployment_commands.record(session, command, run.id, _run_summary(run))
    session.commit()
    return _run_summary(run)
