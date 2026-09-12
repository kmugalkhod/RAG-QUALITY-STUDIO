"""One generation or one metric per delivery; fenced, persisted checkpoints."""

from app.schemas.retrieval import settings_from_node
import copy
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.db.session import engine
from app.models.experiment import Experiment, ExperimentItem
from app.models.pipeline import PipelineVersion
from app.models.query import QueryRun
from app.schemas.query import QueryRequest
from app.services import queries, experiments
from app.evaluation import evaluator
from app.workers.celery_app import celery


def now():
    return datetime.now(timezone.utc)


def next_item(session, job):
    return session.scalar(
        select(ExperimentItem)
        .where(
            ExperimentItem.experiment_id == job.id,
            ExperimentItem.status.in_(["pending", "running"]),
        )
        .order_by(ExperimentItem.ordinal, ExperimentItem.candidate)
        .limit(1)
    )


def output_for(run):
    return {
        "id": str(run.id),
        "answer": run.answer,
        "status": run.status,
        "error": run.error,
        "snapshot": copy.deepcopy(run.snapshot),
    }


def settle(session, job, item):
    selected = job.snapshot["evaluator"]["metrics"]
    if item.output.get("status") == "failed":
        item.error = item.output.get("error")
        item.metrics = {
            m: evaluator.precondition(
                m, job.snapshot["dataset"]["rows"][item.ordinal], item.output
            )
            for m in selected
        }
        item.status = "failed"
    elif all(m in item.metrics for m in selected):
        item.status = "succeeded"
    else:
        item.status = "running"
    job.progress = sum(
        r.status in ("succeeded", "failed") for r in experiments.items(session, job)
    )
    job.execution_token = None
    job.dispatched_at = None
    if job.cancel_requested:
        experiments.finish_cancel(session, job)
    elif job.progress == job.total:
        job.status = "succeeded"
    else:
        job.status = "queued"


def run_step(job_id, db_engine=engine):
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid.uuid4()
    with Session(db_engine) as session:
        job = session.scalar(
            select(Experiment).where(Experiment.id == job_id).with_for_update()
        )
        if job is None or job.status != "queued":
            return
        if job.cancel_requested:
            experiments.finish_cancel(session, job)
            session.commit()
            return
        item = next_item(session, job)
        if item is None:
            return
        job.status, job.execution_token, job.started_at = "running", token, now()
        item.status = "running"
        selected = job.snapshot["evaluator"]["metrics"]
        stage = (
            "generation"
            if not item.output
            else next(m for m in selected if m not in item.metrics)
        )
        item.stage = stage
        key = (item.experiment_id, item.candidate, item.ordinal)
        snapshot = copy.deepcopy(job.snapshot)
        project_id = job.project_id
        session.commit()

    def guard():
        with Session(db_engine) as check:
            current = check.get(Experiment, job_id)
            if (
                current.execution_token != token
                or current.cancel_requested
                or current.status != "running"
            ):
                raise evaluator.EvaluationCancelled()

    result = None
    try:
        guard()
        with Session(db_engine) as session:
            item = session.get(ExperimentItem, key)
            question = snapshot["dataset"]["rows"][item.ordinal]
            if stage == "generation":
                candidate = snapshot["candidates"][item.candidate]
                nodes = {n["type"]: n for n in candidate["execution"]["nodes"]}
                version = session.get(PipelineVersion, item.pipeline_version_id)

                # Link the query and experiment checkpoint in the same commit,
                # before making any paid call. Recovery never repeats it.
                def link(run):
                    item.query_run_id = run.id

                run = queries.execute(
                    session,
                    project_id,
                    QueryRequest(
                        index_id=candidate["index_id"],
                        question=question["question"],
                        retrieval=candidate.get("retrieval")
                        or settings_from_node(nodes["retriever"]),
                    ),
                    version=version,
                    config=candidate["generation_config"],
                    template=nodes["prompt"]["template"],
                    defer=True,
                    on_created=link,
                )
                guard()
                result = output_for(queries.finish(session, run, before_provider=guard))
            else:
                result = evaluator.provider_for(snapshot["evaluator"]).score(
                    stage, question, item.output, guard
                )
    except evaluator.EvaluationCancelled:
        result = (
            evaluator.unavailable("cancelled", "skipped")
            if stage != "generation"
            else None
        )
    except Exception:
        result = (
            {
                "status": "failed",
                "answer": None,
                "error": "Query execution failed. Completed results are preserved.",
                "snapshot": {},
            }
            if stage == "generation"
            else evaluator.unavailable(
                "Metric execution failed; no automatic paid retry.", "failed"
            )
        )
    with Session(db_engine) as session:
        job = session.scalar(
            select(Experiment).where(Experiment.id == job_id).with_for_update()
        )
        if job.execution_token != token or job.status != "running":
            return
        item = session.get(ExperimentItem, key)
        if result is not None:
            if stage == "generation":
                item.output = result
            else:
                item.metrics = {**item.metrics, stage: result}
        settle(session, job, item)
        session.commit()


@celery.task(name="experiments.step", soft_time_limit=330, time_limit=360)
def experiment_step(job_id):
    run_step(uuid.UUID(job_id))


def dispatch_experiments_once(db_engine=engine, send=None):
    send = send or (lambda job_id: experiment_step.apply_async(args=[str(job_id)]))
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    current = now()
    with Session(db_engine) as session:
        stale = session.scalars(
            select(Experiment)
            .where(
                Experiment.status == "running",
                Experiment.started_at < current - timedelta(seconds=420),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in stale:
            item = next_item(session, job)
            if item:
                if item.stage == "generation":
                    run = (
                        session.get(QueryRun, item.query_run_id)
                        if item.query_run_id
                        else None
                    )
                    if run and run.status != "running":
                        item.output = output_for(run)
                    else:
                        if run:
                            run.status, run.error = (
                                "failed",
                                "Experiment query interrupted; not retried to avoid duplicate charges.",
                            )
                        item.output = (
                            output_for(run)
                            if run
                            else {
                                "status": "failed",
                                "error": "Worker interrupted before generation checkpoint.",
                                "snapshot": {},
                            }
                        )
                else:
                    item.metrics = {
                        **item.metrics,
                        item.stage: evaluator.unavailable(
                            "Worker interrupted; metric not retried to avoid duplicate charges.",
                            "failed",
                        ),
                    }
                settle(session, job, item)
            else:
                job.status, job.execution_token, job.error = (
                    "failed",
                    None,
                    "Experiment checkpoint missing.",
                )
        session.commit()
    with Session(db_engine) as session:
        jobs = session.scalars(
            select(Experiment)
            .where(
                Experiment.status == "queued",
                or_(
                    Experiment.dispatched_at.is_(None),
                    Experiment.dispatched_at < current - timedelta(seconds=30),
                ),
            )
            .order_by(Experiment.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            send(job.id)
            job.dispatched_at = current
        session.commit()
