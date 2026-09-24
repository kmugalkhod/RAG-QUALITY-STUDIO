from app.schemas.retrieval import algorithm_snapshot
from datetime import datetime, timedelta, timezone
from time import monotonic
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from app.models.query import QueryRun
from app.providers import generation
from app.providers.embeddings import EmbeddingError
from app.pipelines.generation import PROMPT_VERSION
from app.pipelines.langchain_rag import compile_answer_chain, runtime_snapshot
from app.schemas.index import RetrievalRequest
from app.schemas.pipeline import Execution
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
    preview_execution=None,
    preview_base=None,
):
    index = indexes.get_index(session, project_id, request.index_id)
    if index.status != "succeeded":
        raise HTTPException(
            409, "Select a ready index. Partial indexes cannot be queried."
        )
    pipeline_execution = preview_execution or (version.execution if version else None)
    node_ids = (
        {node["type"]: node["id"] for node in pipeline_execution["nodes"]}
        if pipeline_execution
        else None
    )
    snapshot = dict(
        top_k=request.top_k,
        retrieval=request.retrieval.model_dump(),
        retrieval_algorithm=algorithm_snapshot(),
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
        pipeline_execution=pipeline_execution,
        execution_engine=runtime_snapshot(node_ids),
        pipeline_preview=preview_execution is not None,
        base_pipeline_id=str(preview_base.pipeline_id) if preview_base else None,
        base_version_id=str(preview_base.id) if preview_base else None,
        base_version=preview_base.version if preview_base else None,
        pipeline_name=preview_base.name
        if preview_base
        else (version.name if version else None),
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
    snapshot = dict(run.snapshot)
    trace = None
    try:
        execution_data = snapshot.get("pipeline_execution")
        if execution_data:
            execution = Execution.model_validate(execution_data)
            nodes = {node.type: node for node in execution.nodes}
            retriever_node = nodes["retriever"]
            if retriever_node.index_id != run.index_id:
                raise generation.GenerationError(
                    "The saved pipeline index does not match this query run."
                )
            retrieval = retriever_node.settings
            prompt_template = nodes["prompt"].template
            llm_node = nodes["llm"]
            node_ids = {kind: node.id for kind, node in nodes.items()}
        else:
            retrieval = snapshot.get("retrieval") or {
                "mode": "vector",
                "top_k": snapshot["top_k"],
            }
            prompt_template = snapshot.get("prompt_template")
            node_ids = None
        request = QueryRequest(
            index_id=run.index_id,
            question=run.question,
            retrieval=retrieval,
        )
        config = snapshot.get("generation_config") or generation.configured()
        if execution_data:
            config = {
                **config,
                "model": llm_node.model,
                "max_tokens": llm_node.max_tokens,
                "temperature": llm_node.temperature,
            }
        snapshot["generation_config"] = config
        index = indexes.get_index(session, project_id, run.index_id)

        def checkpoint(updates):
            snapshot.update(jsonable_encoder(updates))
            run.snapshot = dict(snapshot)
            session.commit()

        chain, trace = compile_answer_chain(
            session=session,
            project_id=project_id,
            index=index,
            request=RetrievalRequest(
                index_id=run.index_id,
                query=request.question,
                retrieval=request.retrieval,
            ),
            generation_config=config,
            prompt_template=prompt_template,
            node_ids=node_ids,
            checkpoint=checkpoint,
            before_provider=before_provider,
        )
        result = chain.invoke(
            {"question": request.question},
            config={"run_name": "validated_answer_pipeline"},
        )
        snapshot.update(jsonable_encoder(trace.updates))
        answer = result["answer"]
        if result["finish_reason"] != "stop":
            raise generation.GenerationError(
                "OpenRouter generation did not finish normally (output limit or filtering). Try a shorter question or adjust output capacity."
            )
        run.answer = answer
        run.status = (
            "insufficient_evidence"
            if answer.startswith("INSUFFICIENT_EVIDENCE")
            else "succeeded"
        )
    except (generation.GenerationError, EmbeddingError) as exc:
        run.status, run.error = "failed", str(exc)
    except Exception:
        session.rollback()
        run.status, run.error = (
            "failed",
            "Query execution failed. Retry or check server configuration.",
        )
    if trace is not None:
        snapshot.update(jsonable_encoder(trace.updates))
    snapshot["total_ms"] = round((monotonic() - started) * 1000, 3)
    run.snapshot = dict(snapshot)
    session.commit()
    session.refresh(run)
    return run
