from datetime import datetime, timedelta, timezone
from time import monotonic
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from app.models.query import QueryRun
from app.providers import generation
from app.providers.embeddings import EmbeddingError
from app.pipelines.generation import PROMPT_VERSION, build_context, validate_citations
from app.schemas.index import RetrievalRequest
from app.services import indexes
from app.services.documents import project, paginate


def recover(session, project_id):
    session.execute(
        update(QueryRun)
        .where(
            QueryRun.project_id == project_id,
            QueryRun.status == "running",
            QueryRun.created_at < datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        .values(
            status="failed",
            error="Query execution was interrupted. Submit a new question to retry.",
        )
    )
    session.commit()


def list_runs(session, project_id, limit, offset):
    project(session, project_id)
    recover(session, project_id)
    return paginate(
        session,
        select(QueryRun)
        .where(QueryRun.project_id == project_id)
        .order_by(QueryRun.created_at.desc(), QueryRun.id),
        limit,
        offset,
    )


def get_run(session, project_id, run_id):
    recover(session, project_id)
    run = session.scalar(
        select(QueryRun).where(QueryRun.id == run_id, QueryRun.project_id == project_id)
    )
    if run is None:
        raise HTTPException(404, "Query run not found in this project.")
    return run


def execute(
    session,
    project_id,
    request,
    *,
    version=None,
    config=None,
    template=None,
    defer=False,
    on_created=None,
):
    index = indexes.get_index(session, project_id, request.index_id)
    if index.status != "succeeded":
        raise HTTPException(
            409, "Select a ready index. Partial indexes cannot be queried."
        )
    snapshot = dict(
        top_k=request.top_k,
        prompt_version="grounded-pipeline-template-v1" if template else PROMPT_VERSION,
        evidence=[],
        messages=[],
        retrieval_ms=None,
        generation_ms=None,
        total_ms=None,
        usage=None,
        cost_usd=None,
        cost_basis=None,
        embedding_config=index.embedding_config,
        generation_config=config,
        prompt_template=template,
        pipeline_version=version.version if version else None,
        pipeline_execution=version.execution if version else None,
    )
    run = QueryRun(
        project_id=project_id,
        pipeline_version_id=version.id if version else None,
        index_id=index.id,
        index_version=index.version,
        question=request.question,
        snapshot=snapshot,
    )
    session.add(run)
    session.flush()
    if on_created:
        on_created(run)
    session.commit()
    if defer:
        return run
    return finish(session, run)


def finish(session, run, *, before_provider=None):
    from app.schemas.query import QueryRequest

    started = monotonic()
    project_id = run.project_id
    request = QueryRequest(
        index_id=run.index_id, question=run.question, top_k=run.snapshot["top_k"]
    )
    snapshot = dict(run.snapshot)
    stage = None
    stage_start = started
    try:
        config = snapshot.get("generation_config") or generation.configured()
        snapshot["generation_config"] = config
        stage = "retrieval_ms"
        stage_start = monotonic()
        if before_provider:
            before_provider()
        result = indexes.retrieve(
            session,
            project_id,
            RetrievalRequest(
                index_id=run.index_id, query=request.question, top_k=request.top_k
            ),
        )
        snapshot[stage] = round((monotonic() - stage_start) * 1000, 3)
        stage = None
        sources, messages = build_context(
            request.question,
            jsonable_encoder(result["items"]),
            config,
            snapshot.get("prompt_template"),
        )
        snapshot.update(
            evidence=sources,
            messages=messages,
            retrieved_count=len(result["items"]),
            omitted_count=len(result["items"]) - len(sources),
        )
        # Checkpoint evidence before the potentially billable call.
        run.snapshot = dict(snapshot)
        session.commit()
        if not sources:
            answer = "INSUFFICIENT_EVIDENCE: No evidence was retrieved from this index."
            snapshot["generation_ms"] = 0
        else:
            stage = "generation_ms"
            stage_start = monotonic()
            if before_provider:
                before_provider()
            completion = generation.provider_for().generate(messages, config)
            snapshot[stage] = round((monotonic() - stage_start) * 1000, 3)
            stage = None
            answer = completion.answer
            snapshot.update(
                actual_model=completion.model,
                finish_reason=completion.finish_reason,
                usage=completion.usage,
                cost_usd=completion.cost_usd,
                cost_basis="OpenRouter reported generation cost (USD); excludes retrieval embeddings"
                if completion.cost_usd is not None
                else None,
            )
            if completion.finish_reason != "stop":
                raise generation.GenerationError(
                    "OpenRouter generation did not finish normally (output limit or filtering). Try a shorter question or adjust output capacity."
                )
        run.answer = answer
        run.status = (
            "insufficient_evidence"
            if answer.startswith("INSUFFICIENT_EVIDENCE")
            else "succeeded"
        )
        snapshot["citations"] = validate_citations(answer, sources)
    except (generation.GenerationError, EmbeddingError) as exc:
        run.status, run.error = "failed", str(exc)
    except Exception:
        session.rollback()
        run.status, run.error = (
            "failed",
            "Query execution failed. Retry or check server configuration.",
        )
    if stage:
        snapshot[stage] = round((monotonic() - stage_start) * 1000, 3)
    snapshot["total_ms"] = round((monotonic() - started) * 1000, 3)
    run.snapshot = dict(snapshot)
    session.commit()
    session.refresh(run)
    return run
