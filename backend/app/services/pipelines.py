from dataclasses import asdict

from fastapi import HTTPException
from sqlalchemy import select, func
from app.connectors.website import WebsiteScopeTooLarge, resolve_website_fetch_policy
from app.core.config import settings
from app.models.document import Document
from app.models.connection import SourceConnection
from app.models.index import KnowledgeSet
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.query import QueryRun
from app.providers import chat_models, generation
from app.schemas.ingestion import IngestionExecution
from app.schemas.pipeline import DEFAULT_TEMPLATE, Execution
from app.schemas.query import QueryRequest
from app.services import indexes, provider_credentials, queries
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


def options(session, project_id, principal):
    """Models and limits the answer editor may offer, with the reason when unusable."""
    project(session, project_id)
    error = error_code = None
    with provider_credentials.bound_for_project(session, project_id):
        models = chat_models.available()
        try:
            generation.configured()
        except generation.GenerationError as exc:
            error, error_code = str(exc), exc.code
    return {
        "models": [m.id for m in models],
        "model_options": [asdict(m) for m in models],
        "default_model": chat_models.default_model(models),
        "max_tokens": settings.chat_max_tokens,
        "context_tokens": settings.chat_context_tokens,
        "template": DEFAULT_TEMPLATE,
        "error": error,
        "error_code": error_code,
        "can_manage_models": provider_credentials.can_manage(principal),
    }


def validate_answer(session, project_id, execution):
    nodes = {n.type: n for n in execution.nodes}
    index = indexes.get_index(session, project_id, nodes["retriever"].index_id)
    if index.status != "succeeded":
        raise HTTPException(
            409, "Select a ready index. Partial indexes cannot be queried."
        )
    llm = nodes["llm"]
    try:
        with provider_credentials.bound_for_project(session, project_id):
            config = generation.configured(llm.model, llm.max_tokens, llm.temperature)
    except generation.GenerationError as exc:
        raise HTTPException(422, str(exc)) from None
    return nodes, config


# Existing query and experiment services use this answer-only validation entry
# point. Keep it stable while ingestion dispatch remains a separate path.
validate = validate_answer


def website_fetch_policies(execution: IngestionExecution) -> dict[str, dict]:
    """Resolve the effective fetch policy of every Website source node."""
    policies = {}
    for position, node in enumerate(execution.nodes):
        if node.type == "source" and node.config.kind == "website":
            try:
                policy = resolve_website_fetch_policy(node.config, settings)
            except WebsiteScopeTooLarge as exc:
                # Shaped like a validation issue so the editor shows it on the
                # node's Maximum pages field.
                raise HTTPException(
                    422,
                    [
                        {
                            "loc": [
                                "execution",
                                "nodes",
                                position,
                                "config",
                                "website",
                                "max_pages",
                            ],
                            "msg": str(exc),
                            "type": "value_error",
                        }
                    ],
                ) from None
            policies[node.id] = policy.model_dump(mode="json")
    return policies


MAX_WEBSITE_SOURCES = 5
# All Website sources of one pipeline together; each keeps its own 1–1,000 limit.
MAX_WEBSITE_RUN_PAGES = 2500


def validate_source_combination(execution: IngestionExecution):
    """Rules for newly saved versions only; saved versions keep running as before."""
    sources = [
        (position, node)
        for position, node in enumerate(execution.nodes)
        if node.type == "source"
    ]
    if len(sources) < 2:
        return
    first_kind = sources[0][1].config.kind
    for position, node in sources[1:]:
        if node.config.kind != first_kind:
            raise HTTPException(
                422,
                [
                    {
                        "loc": ["execution", "nodes", position, "config", "kind"],
                        "msg": (
                            "Sources in one pipeline must use the same connector. "
                            "Mixing connectors is not supported yet."
                        ),
                        "type": "value_error",
                    }
                ],
            )
    if first_kind == "website" and len(sources) > MAX_WEBSITE_SOURCES:
        raise HTTPException(
            422,
            [
                {
                    "loc": ["execution", "nodes"],
                    "msg": (
                        f"A pipeline can read at most {MAX_WEBSITE_SOURCES} "
                        "Website sources."
                    ),
                    "type": "value_error",
                }
            ],
        )
    if first_kind == "website":
        total = sum(node.config.max_pages for _, node in sources)
        if total > MAX_WEBSITE_RUN_PAGES:
            # Reported on every source's Maximum pages field, since lowering
            # any of them can fix it.
            raise HTTPException(
                422,
                [
                    {
                        "loc": [
                            "execution",
                            "nodes",
                            position,
                            "config",
                            "website",
                            "max_pages",
                        ],
                        "msg": (
                            f"All Website sources together may fetch at most "
                            f"{MAX_WEBSITE_RUN_PAGES:,} pages; they now allow "
                            f"{total:,}. Lower Maximum pages on one or more sources."
                        ),
                        "type": "value_error",
                    }
                    for position, _ in sources
                ],
            )


def validate_ingestion(session, project_id, execution: IngestionExecution):
    from app.ingestion_content.extractors.pdf import installed_ocr_languages

    website_fetch_policies(execution)

    requested_ocr = {
        language
        for node in execution.nodes
        if node.type == "extract" and hasattr(node, "ocr") and node.ocr.mode != "off"
        for language in node.ocr.languages
    }
    if requested_ocr:
        unavailable = requested_ocr - set(installed_ocr_languages())
        if unavailable:
            raise HTTPException(
                422,
                "OCR language packs are unavailable on this server: "
                + ", ".join(sorted(unavailable))
                + ". Choose installed languages before saving or running.",
            )
    document_ids = {
        document_id
        for node in execution.nodes
        if node.type == "source" and node.config.kind == "existing_files"
        for document_id in node.config.document_ids
    }
    if document_ids:
        found = set(
            session.scalars(
                select(Document.id).where(
                    Document.project_id == project_id,
                    Document.origin_kind == "upload",
                    Document.id.in_(document_ids),
                )
            )
        )
        if found != document_ids:
            raise HTTPException(
                404, "One or more source documents were not found in this project."
            )
    s3_connections = {
        node.config.connection_id
        for node in execution.nodes
        if node.type == "source" and node.config.kind == "s3"
    }
    if s3_connections:
        if not settings.source_connections_enabled:
            raise HTTPException(503, "Source connection management is not enabled.")
        found = set(
            session.scalars(
                select(SourceConnection.id).where(
                    SourceConnection.project_id == project_id,
                    SourceConnection.kind == "s3",
                    SourceConnection.id.in_(s3_connections),
                )
            )
        )
        if found != s3_connections:
            raise HTTPException(
                404, "One or more S3 connections were not found in this project."
            )
    notion_connections = {
        node.config.connection_id
        for node in execution.nodes
        if node.type == "source" and node.config.kind == "notion"
    }
    if notion_connections:
        if not settings.source_connections_enabled:
            raise HTTPException(503, "Source connection management is not enabled.")
        found = set(
            session.scalars(
                select(SourceConnection.id).where(
                    SourceConnection.project_id == project_id,
                    SourceConnection.kind == "notion",
                    SourceConnection.id.in_(notion_connections),
                )
            )
        )
        if found != notion_connections:
            raise HTTPException(
                404, "One or more Notion connections were not found in this project."
            )
    confluence_connections = {
        node.config.connection_id
        for node in execution.nodes
        if node.type == "source" and node.config.kind == "confluence"
    }
    if confluence_connections:
        if not settings.source_connections_enabled:
            raise HTTPException(503, "Source connection management is not enabled.")
        found = set(
            session.scalars(
                select(SourceConnection.id).where(
                    SourceConnection.project_id == project_id,
                    SourceConnection.kind == "confluence",
                    SourceConnection.id.in_(confluence_connections),
                )
            )
        )
        if found != confluence_connections:
            raise HTTPException(
                404,
                "One or more Confluence connections were not found in this project.",
            )
    embed = next(node for node in execution.nodes if node.type == "embed")
    expected = (
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.embedding_revision,
    )
    actual = (embed.provider, embed.model, embed.dimensions, embed.config_version)
    if actual != expected:
        raise HTTPException(
            422,
            "Embedding settings must match the server's configured provider, model, dimensions and revision.",
        )
    publish = next(node for node in execution.nodes if node.type == "publish_index")
    if publish.knowledge_set_id is not None:
        knowledge_set = session.scalar(
            select(KnowledgeSet).where(
                KnowledgeSet.id == publish.knowledge_set_id,
                KnowledgeSet.project_id == project_id,
            )
        )
        if knowledge_set is None:
            raise HTTPException(404, "Knowledge set not found in this project.")
        if knowledge_set.name != publish.knowledge_set_name:
            raise HTTPException(
                409, "The knowledge-set name does not match its saved identity."
            )


def save(session, project_id, request, pipeline_id=None):
    project(session, project_id)
    if request.kind == "answer":
        validate_answer(session, project_id, request.execution)
    else:
        validate_source_combination(request.execution)
        validate_ingestion(session, project_id, request.execution)
    if pipeline_id is None:
        row = Pipeline(project_id=project_id, name=request.name, kind=request.kind)
        session.add(row)
        session.flush()
    else:
        row = get_pipeline(session, project_id, pipeline_id)
        if row.kind != request.kind:
            raise HTTPException(
                409, "A pipeline version must use the parent pipeline's kind."
            )
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


def list_pipelines(session, project_id, limit, offset, kind=None):
    project(session, project_id)
    statement = select(Pipeline).where(Pipeline.project_id == project_id)
    if kind is not None:
        statement = statement.where(Pipeline.kind == kind)
    return paginate(
        session,
        statement.order_by(Pipeline.created_at.desc(), Pipeline.id),
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
    pipeline = get_pipeline(session, project_id, pipeline_id)
    if pipeline.kind != "answer":
        raise HTTPException(
            409, "Ingestion pipeline versions cannot run through the answer endpoint."
        )
    version = get_version(session, project_id, pipeline_id, version_id)
    nodes, config = validate_answer(
        session, project_id, Execution.model_validate(version.execution)
    )
    retriever = nodes["retriever"]
    return queries.execute(
        session,
        project_id,
        QueryRequest(
            index_id=retriever.index_id,
            retrieval=retriever.settings,
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
        pipeline = get_pipeline(session, project_id, request.base_pipeline_id)
        if pipeline.kind != "answer":
            raise HTTPException(
                409, "Ingestion pipeline versions cannot be used as answer previews."
            )
        base = get_version(
            session, project_id, request.base_pipeline_id, request.base_version_id
        )
    nodes, config = validate_answer(session, project_id, request.execution)
    retriever = nodes["retriever"]
    return queries.execute(
        session,
        project_id,
        QueryRequest(
            index_id=retriever.index_id,
            retrieval=retriever.settings,
            question=request.question,
        ),
        config=config,
        template=nodes["prompt"].template,
        preview_execution=request.execution.model_dump(mode="json"),
        preview_base=base,
        defer=True,
    )
