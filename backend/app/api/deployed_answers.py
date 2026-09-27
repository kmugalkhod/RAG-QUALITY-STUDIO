"""Loopback-only server-to-server deployed answer API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import Database
from app.core.auth import _loopback_request
from app.core.deployment_auth import verify_key
from app.models.deployment import AnswerDeployment, AnswerDeploymentRelease
from app.models.deployment import DeployedAnswerRun
from app.db.session import get_deployment_session
from app.schemas.deployment import QuestionInput
from app.services import deployed_runs
from app.services.deployments import _validated_release

router = APIRouter(prefix="/v1/answer-deployments")
AdmissionDatabase = Annotated[Session, Depends(get_deployment_session)]


def _deployment(session, request, deployment_id):
    if not _loopback_request(request):
        raise HTTPException(403, "Deployment access is restricted to loopback.")
    row = session.get(AnswerDeployment, deployment_id)
    if row is None:
        raise HTTPException(404, "Answer deployment not found.")
    return row


def _server_request(request):
    if request.headers.get("origin"):
        raise HTTPException(403, "Browser-origin deployment requests are disabled.")


@router.get("/{deployment_id}/status")
def status(
    deployment_id: UUID,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    row = _deployment(session, request, deployment_id)
    _server_request(request)
    verify_key(session, row, authorization)
    session.commit()
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


@router.post("/{deployment_id}/questions", status_code=202)
def question(
    deployment_id: UUID,
    payload: QuestionInput,
    request: Request,
    response: Response,
    session: AdmissionDatabase,
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    row = _deployment(session, request, deployment_id)
    _server_request(request)
    key = verify_key(session, row, authorization)
    run, replay = deployed_runs.admit(
        session, row, key, payload.question, idempotency_key or ""
    )
    release = session.get(AnswerDeploymentRelease, run.release_id)
    response.status_code = 200 if replay else 202
    response.headers["Cache-Control"] = "no-store"
    return deployed_runs.accepted(run, release)


def _own_run(session, deployment, client_id, run_id):
    run = session.scalar(
        select(DeployedAnswerRun).where(
            DeployedAnswerRun.id == run_id,
            DeployedAnswerRun.deployment_id == deployment.id,
            DeployedAnswerRun.client_id == client_id,
        )
    )
    if run is None:
        raise HTTPException(404, "Question not found.")
    if run.redacted_at is not None:
        raise HTTPException(410, "Result expired.")
    return run


@router.get("/{deployment_id}/questions/{run_id}/status")
def question_status(
    deployment_id: UUID,
    run_id: UUID,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    row = _deployment(session, request, deployment_id)
    _server_request(request)
    key = verify_key(session, row, authorization)
    session.commit()
    run = _own_run(session, row, key.client_id, run_id)
    response.headers["Cache-Control"] = "no-store"
    return deployed_runs.status(run)


@router.get("/{deployment_id}/questions/{run_id}/result")
def question_result(
    deployment_id: UUID,
    run_id: UUID,
    request: Request,
    response: Response,
    session: Database,
    authorization: Annotated[str | None, Header()] = None,
):
    row = _deployment(session, request, deployment_id)
    _server_request(request)
    key = verify_key(session, row, authorization)
    session.commit()
    run = _own_run(session, row, key.client_id, run_id)
    response.headers["Cache-Control"] = "no-store"
    if run.status not in {"succeeded", "insufficient_evidence", "failed", "cancelled"}:
        response.status_code = 202
        return deployed_runs.status(run)
    if run.status in {"failed", "cancelled"}:
        return {
            "id": run.id,
            "status": run.status,
            "error_code": run.error_code,
            "message": run.error_message or "The answer could not be completed.",
        }
    release = session.get(AnswerDeploymentRelease, run.release_id)
    return {
        "id": run.id,
        "status": run.status,
        "answer": run.answer,
        "insufficient_evidence": run.status == "insufficient_evidence",
        "release_number": release.release_number,
        "citations": run.citations or [],
        "usage": run.usage,
        "cost_usd": None,
        "cost_basis": "Total query cost is unavailable; the full admission reservation remains held.",
        "timing_ms": run.timing_ms,
    }
