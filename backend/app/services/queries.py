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


def execute(session, project_id, request):
    index = indexes.get_index(session, project_id, request.index_id)
    if index.status != "succeeded":
        raise HTTPException(
            409, "Select a ready index. Partial indexes cannot be queried."
        )
    started = monotonic()
    snapshot = dict(
        top_k=request.top_k,
        prompt_version=PROMPT_VERSION,
        evidence=[],
        messages=[],
        retrieval_ms=None,
        generation_ms=None,
        total_ms=None,
        usage=None,
        cost_usd=None,
        cost_basis=None,
        embedding_config=index.embedding_config,
    )
    run = QueryRun(
        project_id=project_id,
        index_id=index.id,
        index_version=index.version,
        question=request.question,
        snapshot=snapshot,
    )
    session.add(run)
    session.commit()
    stage = None
    stage_start = started
    try:
        config = generation.configured()
        snapshot["generation_config"] = config
        stage = "retrieval_ms"
        stage_start = monotonic()
        result = indexes.retrieve(
            session,
            project_id,
            RetrievalRequest(
                index_id=index.id, query=request.question, top_k=request.top_k
            ),
        )
        snapshot[stage] = round((monotonic() - stage_start) * 1000, 3)
        stage = None
        sources, messages = build_context(
            request.question, jsonable_encoder(result["items"]), config
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
