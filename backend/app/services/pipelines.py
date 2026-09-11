from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.query import QueryRun
from app.providers import generation
from app.schemas.pipeline import Execution
from app.schemas.query import QueryRequest
from app.services import indexes, queries
from app.services.documents import project, paginate


def get_pipeline(session, project_id, pipeline_id):
    row = session.scalar(
        select(Pipeline).where(
            Pipeline.id == pipeline_id, Pipeline.project_id == project_id
        )
    )
    if row is None:
        raise HTTPException(404, "Pipeline not found in this project.")
    return row


def get_version(session, project_id, pipeline_id, version_id):
    get_pipeline(session, project_id, pipeline_id)
    row = session.scalar(
        select(PipelineVersion).where(
            PipelineVersion.id == version_id,
            PipelineVersion.pipeline_id == pipeline_id,
            PipelineVersion.project_id == project_id,
        )
    )
    if row is None:
        raise HTTPException(404, "Pipeline version not found in this project.")
    return row


def validate(session, project_id, execution):
    nodes = {n.type: n for n in execution.nodes}
    index = indexes.get_index(session, project_id, nodes["retriever"].index_id)
    if index.status != "succeeded":
        raise HTTPException(
            409, "Select a ready index. Partial indexes cannot be queried."
        )
    llm = nodes["llm"]
    try:
        config = generation.configured(llm.model, llm.max_tokens, llm.temperature)
    except generation.GenerationError as exc:
        raise HTTPException(422, str(exc)) from None
    return nodes, config


def save(session, project_id, request, pipeline_id=None):
    project(session, project_id)
    validate(session, project_id, request.execution)
    if pipeline_id is None:
        row = Pipeline(project_id=project_id, name=request.name)
        session.add(row)
        session.flush()
    else:
        row = get_pipeline(session, project_id, pipeline_id)
        # Serialize version numbering; concurrent REPEATABLE READ writes may return
        # the application's safe database error and can be manually retried.
        session.refresh(row, with_for_update=True)
        row.name = request.name
    number = (
        session.scalar(
            select(func.max(PipelineVersion.version)).where(
                PipelineVersion.pipeline_id == row.id
            )
        )
        or 0
    ) + 1
    version = PipelineVersion(
        pipeline_id=row.id,
        project_id=project_id,
        version=number,
        name=request.name,
        execution=request.execution.model_dump(mode="json"),
        layout=request.layout.model_dump(mode="json"),
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return version


def list_pipelines(session, project_id, limit, offset):
    project(session, project_id)
    return paginate(
        session,
        select(Pipeline)
        .where(Pipeline.project_id == project_id)
        .order_by(Pipeline.created_at.desc(), Pipeline.id),
        limit,
        offset,
    )


def list_versions(session, project_id, pipeline_id, limit, offset):
    get_pipeline(session, project_id, pipeline_id)
    return paginate(
        session,
        select(PipelineVersion)
        .where(PipelineVersion.pipeline_id == pipeline_id)
        .order_by(PipelineVersion.version.desc()),
        limit,
        offset,
    )


def start(session, project_id, pipeline_id, version_id, request):
    version = get_version(session, project_id, pipeline_id, version_id)
    nodes, config = validate(
        session, project_id, Execution.model_validate(version.execution)
    )
    retriever = nodes["retriever"]
    return queries.execute(
        session,
        project_id,
        QueryRequest(
            index_id=retriever.index_id,
            top_k=retriever.top_k,
            question=request.question,
        ),
        version=version,
        config=config,
        template=nodes["prompt"].template,
        defer=True,
    )


def finish_run(run_id):
    from sqlalchemy.orm import Session
    from app.db.session import engine

    with Session(engine) as session:
        run = session.get(QueryRun, run_id)
        if run is not None and run.status == "running":
            queries.finish(session, run)


def preview(session, project_id, request):
    """Persist an exact test snapshot without creating or changing saved versions."""
    project(session, project_id)
    base = None
    if request.base_pipeline_id is not None:
        base = get_version(
            session, project_id, request.base_pipeline_id, request.base_version_id
        )
    nodes, config = validate(session, project_id, request.execution)
    retriever = nodes["retriever"]
    return queries.execute(
        session,
        project_id,
        QueryRequest(
            index_id=retriever.index_id,
            top_k=retriever.top_k,
            question=request.question,
        ),
        config=config,
        template=nodes["prompt"].template,
        preview_execution=request.execution.model_dump(mode="json"),
        preview_base=base,
        defer=True,
    )
