"""Fenced Celery execution of accepted server-to-server answer runs."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import monotonic
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.models.deployment import (
    AnswerDeployment,
    AnswerDeploymentRelease,
    DeployedAnswerRun,
    DeploymentUsageBucket,
    DeploymentUsageEntry,
)
from app.models.index import IndexVersion
from app.pipelines.langchain_rag import compile_answer_chain
from app.providers import generation
from app.schemas.index import RetrievalRequest
from app.schemas.pipeline import Execution
from app.services import provider_credentials
from app.services.deployments import _hash
from app.workers.celery_app import celery


class Fenced(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def _session(db_engine=engine):
    if isinstance(db_engine, Connection):
        return Session(db_engine, join_transaction_mode="create_savepoint")
    return Session(db_engine.execution_options(isolation_level="READ COMMITTED"))


def _owned(session, run_id, token):
    row = session.scalar(
        select(DeployedAnswerRun)
        .where(
            DeployedAnswerRun.id == run_id,
            DeployedAnswerRun.execution_token == token,
            DeployedAnswerRun.status.in_(["running", "cancel_requested"]),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise Fenced()
    return row


def _release_reservation(session, run):
    exists = session.scalar(
        select(DeploymentUsageEntry.id).where(
            DeploymentUsageEntry.run_id == run.id,
            DeploymentUsageEntry.entry_type == "release",
        )
    )
    if exists is not None or run.provider_call_started_at is not None:
        return
    day = run.created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    for period, start in (("day", day), ("month", month)):
        bucket = session.scalar(
            select(DeploymentUsageBucket)
            .where(
                DeploymentUsageBucket.organization_id == run.organization_id,
                DeploymentUsageBucket.period == period,
                DeploymentUsageBucket.period_start == start,
            )
            .with_for_update()
        )
        if bucket is not None:
            bucket.reserved_usd -= run.cost_reservation_usd
    session.add(
        DeploymentUsageEntry(
            run_id=run.id,
            organization_id=run.organization_id,
            entry_type="release",
            amount_usd=run.cost_reservation_usd,
            basis="no_paid_provider_call",
        )
    )


def claim(run_id, db_engine=engine):
    with _session(db_engine) as session:
        session.execute(select(func.pg_advisory_xact_lock(745199391)))
        run = session.scalar(
            select(DeployedAnswerRun)
            .where(DeployedAnswerRun.id == run_id)
            .with_for_update()
        )
        if run is None or run.status != "queued":
            return None
        deployment_running = session.scalar(
            select(func.count())
            .select_from(DeployedAnswerRun)
            .where(
                DeployedAnswerRun.deployment_id == run.deployment_id,
                DeployedAnswerRun.status.in_(["running", "cancel_requested"]),
            )
        )
        org_running = session.scalar(
            select(func.count())
            .select_from(DeployedAnswerRun)
            .where(
                DeployedAnswerRun.organization_id == run.organization_id,
                DeployedAnswerRun.status.in_(["running", "cancel_requested"]),
            )
        )
        deployment = session.get(AnswerDeployment, run.deployment_id)
        if (
            deployment_running
            >= min(settings.deployment_concurrency, deployment.concurrent_runs)
            or org_running >= settings.deployment_org_concurrency
        ):
            run.dispatched_at = None
            session.commit()
            return None
        token = uuid4()
        run.status = "running"
        run.stage = "claim"
        run.execution_token = token
        run.attempts += 1
        run.started_at = now()
        run.heartbeat_at = run.started_at
        run.deadline_at = run.started_at + timedelta(seconds=100)
        session.commit()
        return token


def _before_call(session, run_id, token, stage):
    run = _owned(session, run_id, token)
    if run.status == "cancel_requested":
        run.status = "cancelled"
        run.finished_at = now()
        run.execution_token = None
        _release_reservation(session, run)
        session.commit()
        raise Fenced()
    run.provider_call_started_at = run.provider_call_started_at or now()
    run.stage = stage
    run.heartbeat_at = now()
    session.commit()


def _checkpoint(session, run_id, token, updates):
    run = _owned(session, run_id, token)
    if run.status == "cancel_requested":
        run.status = "cancelled"
        run.finished_at = now()
        run.execution_token = None
        session.commit()
        raise Fenced()
    evidence = jsonable_encoder(updates.get("evidence") or [])
    run.evidence = [
        {
            "label": str(item.get("label", ""))[:20],
            "document_id": str(item.get("document_id", "")),
            "filename": str(item.get("filename", ""))[:300],
            "page_number": item.get("page_number"),
            "rank": item.get("rank"),
            "text": str(item.get("text", ""))[:2000],
        }
        for item in evidence[:50]
    ]
    run.stage = "evidence"
    run.heartbeat_at = now()
    session.commit()


def _citations(answer, evidence, validation):
    if answer.startswith("INSUFFICIENT_EVIDENCE"):
        return []
    by_label = {item["label"]: item for item in evidence or []}
    result = []
    for label in validation.get("valid", [])[:50]:
        source = by_label.get(label)
        if source is None:
            continue
        result.append(
            {
                "label": label,
                "source_id": source["document_id"],
                "title": source["filename"],
                "page": source["page_number"],
                "excerpt": source["text"][:280],
                "rank": source["rank"],
                "score": None,
            }
        )
    return result


def _finish(
    session, run_id, token, *, result=None, updates=None, error=None, started=None
):
    run = _owned(session, run_id, token)
    if run.status == "cancel_requested":
        run.status = "cancelled"
        run.error_code = "cancelled"
        run.error_message = "The answer was cancelled."
    elif error is not None:
        run.status = "failed"
        run.error_code = (
            "provider_outcome_unknown"
            if run.provider_call_started_at is not None
            else "execution_unavailable"
        )
        run.error_message = (
            "The provider outcome is unknown. Submit a new request only after reviewing usage."
            if run.provider_call_started_at is not None
            else "The answer could not be completed."
        )
    else:
        answer = result["answer"]
        if (
            result["finish_reason"] != "stop"
            or not isinstance(answer, str)
            or len(answer) > 20000
        ):
            run.status = "failed"
            run.error_code = "invalid_provider_result"
            run.error_message = "The answer could not be completed."
        else:
            run.answer = answer
            run.status = (
                "insufficient_evidence"
                if answer.startswith("INSUFFICIENT_EVIDENCE")
                else "succeeded"
            )
            run.citations = _citations(
                answer, run.evidence, updates.get("citations", {})
            )
            run.usage = jsonable_encoder(updates.get("usage"))
            cost = updates.get("cost_usd")
            if cost is not None:
                run.provider_cost_usd = Decimal(str(cost))
            run.timing_ms = {
                "queue": round(
                    (run.started_at - run.created_at).total_seconds() * 1000, 3
                ),
                "execution": round((monotonic() - started) * 1000, 3),
                "retrieval": updates.get("retrieval_ms"),
                "generation": updates.get("generation_ms"),
            }
    run.stage = "terminal"
    run.finished_at = now()
    run.heartbeat_at = run.finished_at
    run.execution_token = None
    if run.provider_call_started_at is None:
        _release_reservation(session, run)
    session.commit()
    return run.status


def process_deployed(run_id, db_engine=engine):
    run_id = UUID(str(run_id))
    token = claim(run_id, db_engine)
    if token is None:
        return
    started = monotonic()
    with _session(db_engine) as session:
        try:
            run = _owned(session, run_id, token)
            release = session.get(AnswerDeploymentRelease, run.release_id)
            if release is None or release.execution_sha256 != _hash(release.execution):
                raise ValueError("Release integrity check failed.")
            execution = Execution.model_validate(release.execution)
            nodes = {node.type: node for node in execution.nodes}
            if nodes["retriever"].index_id != release.index_id:
                raise ValueError("Release index mismatch.")
            index = session.scalar(
                select(IndexVersion).where(
                    IndexVersion.id == release.index_id,
                    IndexVersion.project_id == run.project_id,
                    IndexVersion.status == "succeeded",
                )
            )
            if (
                index is None
                or _hash(index.embedding_config) != release.embedding_sha256
            ):
                raise ValueError("Release index unavailable.")
            with provider_credentials.bound_for_project(session, run.project_id):
                llm = nodes["llm"]
                config = generation.configured(
                    llm.model, llm.max_tokens, llm.temperature
                )
                chain, trace = compile_answer_chain(
                    session=session,
                    project_id=run.project_id,
                    index=index,
                    request=RetrievalRequest(
                        index_id=release.index_id,
                        query=run.question,
                        retrieval=nodes["retriever"].settings,
                    ),
                    generation_config=config,
                    prompt_template=nodes["prompt"].template,
                    node_ids={kind: node.id for kind, node in nodes.items()},
                    checkpoint=lambda updates: _checkpoint(
                        session, run_id, token, updates
                    ),
                    before_embedding=lambda: _before_call(
                        session, run_id, token, "embedding_call"
                    ),
                    before_generation=lambda: _before_call(
                        session, run_id, token, "generation_call"
                    ),
                )
                result = chain.invoke({"question": run.question})
            _finish(
                session,
                run_id,
                token,
                result=result,
                updates=trace.updates,
                started=started,
            )
        except Fenced:
            return
        except Exception:
            session.rollback()
            try:
                _finish(session, run_id, token, error=True, started=started)
            except Fenced:
                return


@celery.task(name="deployed_answers.execute", queue="deployed_answers")
def execute_deployed(run_id: str):
    process_deployed(run_id)
