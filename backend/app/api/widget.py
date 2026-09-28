"""Private browser widget API; deployment keys never reach this route family."""

from datetime import datetime, timezone
from typing import Annotated
from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deployed_answers import serialize_result
from app.core.auth import _loopback_request
from app.core.deployment_auth import verify_key
from app.core import widget_auth
from app.db.session import get_deployment_session
from app.models.deployment import (
    AnswerDeployment,
    AnswerDeploymentRelease,
    DeployedAnswerRun,
)
from app.schemas.deployment import QuestionInput, WidgetExchangeInput
from app.services import deployed_runs
from app.services.deployments import _validated_release

router = APIRouter(prefix="/v1/answer-deployments")
Database = Annotated[Session, Depends(get_deployment_session)]


def _deployment(session, deployment_id):
    row = session.get(AnswerDeployment, deployment_id)
    if row is None:
        raise HTTPException(404, "not_found")
    return row


def _principal(session, deployment_id, authorization, origin):
    row = _deployment(session, deployment_id)
    token, key = widget_auth.verify(session, row, authorization, origin)
    return row, token, key


def _config(row):
    return {
        "protocol_version": "1.0.0",
        "deployment_id": row.id,
        "enabled": row.widget_enabled and row.state == "active",
        "public_enabled": row.widget_public_enabled,
        "allowed_origins": row.widget_origins,
        "branding": row.widget_branding
        or {
            "title": "Ask a question",
            "greeting": "How can I help?",
            "color": "blue",
            "position": "right",
        },
    }


@router.get("/{deployment_id}/widget/config")
def config(deployment_id: UUID, response: Response, session: Database):
    row = _deployment(session, deployment_id)
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Referrer-Policy"] = "no-referrer"
    return _config(row)


@router.post("/{deployment_id}/widget-tokens", status_code=201)
def exchange(
    deployment_id: UUID,
    payload: WidgetExchangeInput,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    if request.headers.get("origin") or not _loopback_request(request):
        raise HTTPException(403, "browser_origin_disabled")
    row = _deployment(session, deployment_id)
    key = verify_key(session, row, authorization)
    issued = widget_auth.issue(
        session, row, key, payload.visitor_session_id, payload.site_origin
    )
    response.headers["Cache-Control"] = "no-store"
    return issued


@router.post("/{deployment_id}/widget/public-token", status_code=201)
def public_token(
    deployment_id: UUID,
    payload: WidgetExchangeInput,
    request: Request,
    response: Response,
    session: Database,
):
    if request.headers.get("origin") != widget_auth.settings.widget_frame_origin:
        raise HTTPException(403, "origin_not_allowed")
    row = _deployment(session, deployment_id)
    issued = widget_auth.issue_public(
        session, row, payload.visitor_session_id, payload.site_origin
    )
    response.headers["Cache-Control"] = "no-store"
    return issued


@router.post("/{deployment_id}/widget-tokens/revoke-session", status_code=204)
def revoke_session(
    deployment_id: UUID,
    payload: WidgetExchangeInput,
    request: Request,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    if request.headers.get("origin") or not _loopback_request(request):
        raise HTTPException(403, "browser_origin_disabled")
    row = _deployment(session, deployment_id)
    verify_key(session, row, authorization)
    widget_auth.revoke_visitor(
        session, row, payload.visitor_session_id, payload.site_origin
    )


@router.get("/{deployment_id}/widget/status")
def status(
    deployment_id: UUID,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    row, _, _ = _principal(
        session, deployment_id, authorization, request.headers.get("origin")
    )
    release = (
        session.get(AnswerDeploymentRelease, row.active_release_id)
        if row.active_release_id
        else None
    )
    accepting = row.state == "active" and release is not None
    if accepting:
        try:
            _validated_release(
                session, row, release.pipeline_version_id, release.index_id
            )
        except Exception:
            accepting = False
    response.headers["Cache-Control"] = "no-store"
    return {
        "id": row.id,
        "state": row.state,
        "accepting_questions": accepting,
        "active_release_number": release.release_number if release else None,
    }


@router.post("/{deployment_id}/widget/questions", status_code=202)
def question(
    deployment_id: UUID,
    payload: QuestionInput,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    row, token, key = _principal(
        session, deployment_id, authorization, request.headers.get("origin")
    )
    # The existing admission ledger uses client_id as its idempotency/rate family.
    # For a widget that family is stable for this visitor across token renewal.
    caller = SimpleNamespace(id=key.id, client_id=token.client_id)
    run, replay = deployed_runs.admit(
        session,
        row,
        caller,
        payload.question,
        idempotency_key or "",
        visitor_binding=token.visitor_binding,
    )
    release = session.get(AnswerDeploymentRelease, run.release_id)
    response.status_code = 200 if replay else 202
    response.headers["Cache-Control"] = "no-store"
    return deployed_runs.accepted(run, release, widget=True)


def _owned(session, row, token, run_id):
    run = session.scalar(
        select(DeployedAnswerRun).where(
            DeployedAnswerRun.id == run_id,
            DeployedAnswerRun.deployment_id == row.id,
            DeployedAnswerRun.organization_id == row.organization_id,
            DeployedAnswerRun.project_id == row.project_id,
            DeployedAnswerRun.caller_kind == "widget",
            DeployedAnswerRun.widget_visitor_binding == token.visitor_binding,
        )
    )
    if run is None:
        raise HTTPException(404, "not_found")
    if run.redacted_at is not None or run.result_expires_at <= datetime.now(
        timezone.utc
    ):
        raise HTTPException(410, "result_expired")
    return run


@router.get("/{deployment_id}/widget/questions/{run_id}/status")
def question_status(
    deployment_id: UUID,
    run_id: UUID,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    row, token, _ = _principal(
        session, deployment_id, authorization, request.headers.get("origin")
    )
    run = _owned(session, row, token, run_id)
    response.headers["Cache-Control"] = "no-store"
    return deployed_runs.status(run)


@router.get("/{deployment_id}/widget/questions/{run_id}/result")
def question_result(
    deployment_id: UUID,
    run_id: UUID,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    row, token, _ = _principal(
        session, deployment_id, authorization, request.headers.get("origin")
    )
    run = _owned(session, row, token, run_id)
    return serialize_result(session, run, response)


@router.post("/{deployment_id}/widget/revoke", status_code=204)
def revoke(
    deployment_id: UUID,
    request: Request,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    _, token, _ = _principal(
        session, deployment_id, authorization, request.headers.get("origin")
    )
    token.revoked_at = datetime.now(timezone.utc)
    session.commit()
