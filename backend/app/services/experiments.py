from app.schemas.retrieval import algorithm_snapshot
import json
import copy
import csv
import hashlib
import io
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from app.models.experiment import Experiment, ExperimentItem
from app.models.pipeline import PipelineVersion
from app.schemas.pipeline import Execution
from app.schemas.experiment import ExperimentRead, ItemRead
from app.services import datasets, pipelines, indexes
from app.services.documents import project, paginate
from app.evaluation import evaluator


def application_version():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return {"version": "0.1.0", "source_sha256": digest.hexdigest()}


def submit(session, project_id, request):
    project(session, project_id)
    dataset = datasets.get_version(session, project_id, request.dataset_version_id)
    candidates = []
    for version_id in request.pipeline_version_ids:
        version = session.scalar(
            select(PipelineVersion).where(
                PipelineVersion.id == version_id,
                PipelineVersion.project_id == project_id,
            )
        )
        if version is None:
            raise HTTPException(404, "Pipeline version not found in this project.")
        pipeline = pipelines.get_pipeline(session, project_id, version.pipeline_id)
        if pipeline.kind != "answer":
            raise HTTPException(409, "Experiments require answer pipeline versions.")
        nodes, config = pipelines.validate(
            session, project_id, Execution.model_validate(version.execution)
        )
        index = indexes.get_index(session, project_id, nodes["retriever"].index_id)
        candidates.append(
            {
                "id": str(version.id),
                "pipeline_id": str(version.pipeline_id),
                "name": version.name,
                "version": version.version,
                "execution": version.execution,
                "generation_config": config,
                "index_id": str(index.id),
                "index_version": index.version,
                "embedding_config": index.embedding_config,
                "retrieval": nodes["retriever"].settings.model_dump(),
                "retrieval_algorithm": algorithm_snapshot(),
            }
        )
    try:
        judge = evaluator.configured(request.metrics)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    snapshot = copy.deepcopy(
        {
            "dataset": {
                "id": str(dataset.id),
                "version": dataset.version,
                "name": dataset.name,
                "content_hash": dataset.content_hash,
                "rows": dataset.rows,
            },
            "candidates": candidates,
            "evaluator": judge,
            "application": application_version(),
        }
    )
    experiment = Experiment(
        project_id=project_id,
        dataset_version_id=dataset.id,
        name=request.name,
        snapshot=snapshot,
        total=len(dataset.rows) * len(candidates),
    )
    session.add(experiment)
    session.flush()
    for candidate, version_id in enumerate(request.pipeline_version_ids):
        for ordinal in range(len(dataset.rows)):
            session.add(
                ExperimentItem(
                    experiment_id=experiment.id,
                    project_id=project_id,
                    pipeline_version_id=version_id,
                    candidate=candidate,
                    ordinal=ordinal,
                )
            )
    session.commit()
    return experiment


def get(session, project_id, experiment_id, lock=False):
    query = select(Experiment).where(
        Experiment.id == experiment_id, Experiment.project_id == project_id
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise HTTPException(404, "Experiment not found in this project.")
    return row


def listing(session, project_id, limit, offset):
    project(session, project_id)
    return paginate(
        session,
        select(Experiment)
        .where(Experiment.project_id == project_id)
        .order_by(Experiment.created_at.desc(), Experiment.id),
        limit,
        offset,
    )


def items(session, experiment):
    return session.scalars(
        select(ExperimentItem)
        .where(
            ExperimentItem.experiment_id == experiment.id,
            ExperimentItem.project_id == experiment.project_id,
        )
        .order_by(ExperimentItem.ordinal, ExperimentItem.candidate)
    ).all()


def cancel(session, project_id, experiment_id):
    experiment = get(session, project_id, experiment_id, lock=True)
    if experiment.status in ("queued", "running"):
        experiment.cancel_requested = True
        if experiment.status == "queued":
            finish_cancel(session, experiment)
        session.commit()
    return experiment


def finish_cancel(session, experiment):
    experiment.status = "cancelled"
    experiment.execution_token = None
    for item in items(session, experiment):
        if item.status in ("pending", "running"):
            item.status = "skipped"
            item.error = "Cancelled; completed generation and scores are retained."
            item.metrics = {
                **{
                    m: evaluator.unavailable("cancelled", "skipped")
                    for m in experiment.snapshot["evaluator"]["metrics"]
                },
                **item.metrics,
            }


def mean(values):
    return sum(values) / len(values) if values else None


def aggregate(experiment, rows):
    selected = experiment.snapshot["evaluator"]["metrics"]
    summaries = []
    for candidate in range(len(experiment.snapshot["candidates"])):
        subset = [r for r in rows if r.candidate == candidate]
        summary = {
            "candidate": candidate,
            "total": len(subset),
            "completed": sum(r.status in ("succeeded", "failed") for r in subset),
            "generation_failures": sum(
                r.output.get("status") == "failed" for r in subset
            ),
            "skipped": sum(r.status == "skipped" for r in subset),
            "metrics": {},
        }
        for metric in selected:
            values = [
                r.metrics[metric]["value"]
                for r in subset
                if r.metrics.get(metric, {}).get("status") == "succeeded"
            ]
            summary["metrics"][metric] = {
                "mean": mean(values),
                "scored": len(values),
                **{
                    state: sum(
                        r.metrics.get(metric, {}).get("status") == state for r in subset
                    )
                    for state in ["failed", "skipped", "unavailable"]
                },
                "missing_reference": sum(
                    r.metrics.get(metric, {}).get("reason") == "missing_reference"
                    for r in subset
                ),
                "pending": sum(metric not in r.metrics for r in subset),
            }
        latency = [
            r.output["snapshot"]["total_ms"]
            for r in subset
            if r.output.get("snapshot", {}).get("total_ms") is not None
        ]
        summary["query_latency_ms"] = {"mean": mean(latency), "count": len(latency)}
        for name, getter in [
            (
                "generation_cost_usd",
                lambda r: r.output.get("snapshot", {}).get("cost_usd"),
            ),
            (
                "query_tokens",
                lambda r: (r.output.get("snapshot", {}).get("usage") or {}).get(
                    "total_tokens"
                ),
            ),
        ]:
            values = [v for r in subset if (v := getter(r)) is not None]
            summary[name] = {
                "known_sum": sum(values) if values else None,
                "known_count": len(values),
                "total": len(subset),
            }
        costs = [
            r.metrics.get(m, {}).get("evaluation_cost_usd")
            for r in subset
            for m in selected
        ]
        known = [v for v in costs if v is not None]
        summary["evaluation_cost_usd"] = {
            "known_sum": sum(known) if known else None,
            "known_count": len(known),
            "total": len(costs),
        }
        summaries.append(summary)
    paired = {}
    if len(summaries) == 2:
        by_key = {(r.candidate, r.ordinal): r for r in rows}
        for metric in selected:
            pairs = []
            for ordinal in range(len(experiment.snapshot["dataset"]["rows"])):
                a, b = (by_key[(c, ordinal)].metrics.get(metric, {}) for c in (0, 1))
                if a.get("status") == b.get("status") == "succeeded":
                    pairs.append((a["value"], b["value"]))
            paired[metric] = {
                "count": len(pairs),
                "a_mean": mean([a for a, b in pairs]),
                "b_mean": mean([b for a, b in pairs]),
                "b_minus_a": mean([b - a for a, b in pairs]),
            }
    return {"candidates": summaries, "paired": paired}


def detail(session, project_id, experiment_id):
    experiment = get(session, project_id, experiment_id)
    rows = items(session, experiment)
    return {
        **ExperimentRead.model_validate(experiment).model_dump(mode="json"),
        "items": [ItemRead.model_validate(r).model_dump(mode="json") for r in rows],
        "summary": aggregate(experiment, rows),
    }


def safe_cell(value):
    value = "" if value is None else str(value)
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@"))
        or value.startswith(("\t", "\r", "\n"))
        else value
    )


def export_csv(session, project_id, experiment_id):
    experiment = get(session, project_id, experiment_id)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    selected = experiment.snapshot["evaluator"]["metrics"]
    writer.writerow(
        [
            "question",
            "reference_answer",
            "candidate",
            "pipeline_version_id",
            "index_id",
            "status",
            "answer",
            "query_run_id",
            "query_latency_ms",
            "query_tokens",
            "generation_cost_usd",
            "retrieval_settings",
            "retrieved_evidence",
            *[
                f"{m}_{f}"
                for m in selected
                for f in ("value", "status", "reason", "evaluation_cost_usd")
            ],
        ]
    )
    for item in items(session, experiment):
        row = experiment.snapshot["dataset"]["rows"][item.ordinal]
        candidate = experiment.snapshot["candidates"][item.candidate]
        snap = item.output.get("snapshot", {})
        writer.writerow(
            [
                safe_cell(v)
                for v in [
                    row["question"],
                    row["reference_answer"],
                    candidate["name"],
                    candidate["id"],
                    candidate["index_id"],
                    item.status,
                    item.output.get("answer"),
                    item.query_run_id,
                    snap.get("total_ms"),
                    (snap.get("usage") or {}).get("total_tokens"),
                    snap.get("cost_usd"),
                    json.dumps(snap.get("retrieval") or candidate.get("retrieval")),
                    json.dumps(snap.get("retrieval_result")),
                    *[
                        item.metrics.get(m, {}).get(f)
                        for m in selected
                        for f in ("value", "status", "reason", "evaluation_cost_usd")
                    ],
                ]
            ]
        )
    return buffer.getvalue()
