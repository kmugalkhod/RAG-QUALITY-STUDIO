"""Bounded, project-scoped vector/lexical search and rank fusion."""

from time import monotonic

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import aliased

from app.models.document import Chunk, Document, ProcessingRun
from app.models.index import IndexChunk
from app.models.source import SourceItem, SourceRevision
from app.providers import embeddings
from app.schemas.retrieval import algorithm_snapshot


def search(
    session,
    project_id,
    index,
    request,
    config,
    *,
    query_embeddings=None,
):
    settings = request.retrieval
    parent = aliased(Chunk)
    base = (
        select(Chunk, parent, ProcessingRun, Document, SourceItem)
        .select_from(IndexChunk)
        .join(
            Chunk,
            (Chunk.run_id == IndexChunk.run_id) & (Chunk.ordinal == IndexChunk.ordinal),
        )
        .join(ProcessingRun, ProcessingRun.id == Chunk.run_id)
        .join(Document, Document.id == ProcessingRun.document_id)
        .outerjoin(
            parent,
            (parent.run_id == Chunk.run_id) & (parent.ordinal == Chunk.parent_ordinal),
        )
        .outerjoin(SourceRevision, SourceRevision.processing_run_id == ProcessingRun.id)
        .outerjoin(SourceItem, SourceItem.id == SourceRevision.source_item_id)
        .where(IndexChunk.index_id == index.id, Document.project_id == project_id)
    )
    hybrid = settings.mode == "hybrid"
    vector_weight = settings.vector_weight if hybrid else 1.0
    candidates = {}
    diagnostics = {
        "algorithm": algorithm_snapshot(),
        "vector_count": 0,
        "keyword_count": 0,
        "vector_ms": None,
        "keyword_ms": None,
    }
    for branch in ("vector", "keyword"):
        if settings.mode != branch and not hybrid:
            continue
        if hybrid and (
            (branch == "vector" and vector_weight == 0)
            or (branch == "keyword" and vector_weight == 1)
        ):
            continue
        started = monotonic()
        if branch == "vector":
            vector = embeddings.validate_vectors(
                (
                    [query_embeddings.embed_query(request.query)]
                    if query_embeddings is not None
                    else embeddings.provider_for(config).embed([request.query])
                ),
                1,
                index.dimensions,
            )[0]
            score = IndexChunk.embedding.cosine_distance(vector)
            query = base.add_columns(score).where(IndexChunk.embedding.is_not(None))
            if settings.max_vector_distance is not None:
                query = query.where(score <= settings.max_vector_distance)
            query = query.order_by(score, Chunk.run_id, Chunk.ordinal)
            limit = settings.vector_candidates if hybrid else settings.top_k
        else:
            analysis = literal_column("'simple'::regconfig")
            document = func.to_tsvector(analysis, Chunk.text)
            terms = func.websearch_to_tsquery(analysis, request.query)
            score = func.ts_rank_cd(document, terms)
            query = (
                base.add_columns(score)
                .where(document.op("@@")(terms))
                .order_by(score.desc(), Chunk.run_id, Chunk.ordinal)
            )
            limit = settings.keyword_candidates if hybrid else settings.top_k
        rows = session.execute(query.limit(limit)).all()
        diagnostics[f"{branch}_count"] = len(rows)
        diagnostics[f"{branch}_ms"] = round((monotonic() - started) * 1000, 3)
        for rank, (chunk, supplied_parent, run, doc, source_item, score) in enumerate(
            rows, 1
        ):
            key = (str(run.id), chunk.ordinal)
            supplied = supplied_parent or chunk
            item = candidates.setdefault(
                key,
                dict(
                    document_id=doc.id,
                    filename=doc.filename,
                    content_hash=doc.content_hash,
                    run_id=run.id,
                    processing_version=run.version,
                    ordinal=chunk.ordinal,
                    matched_chunk_ordinal=chunk.ordinal,
                    matched_text=chunk.text,
                    supplied_parent_ordinal=(
                        supplied_parent.ordinal if supplied_parent else None
                    ),
                    page_number=supplied.page_number,
                    start_char=supplied.start_char,
                    end_char=supplied.end_char,
                    text=supplied.text,
                    source_url=(
                        source_item.canonical_location if source_item else None
                    ),
                    section_path=supplied.provenance.get("section_path", []),
                    chunk_role=chunk.chunk_role,
                    token_count=supplied.token_count,
                    cosine_distance=None,
                    lexical_score=None,
                    fusion_score=None,
                    vector_rank=None,
                    keyword_rank=None,
                ),
            )
            item[f"{branch}_rank"] = rank
            item["cosine_distance" if branch == "vector" else "lexical_score"] = float(
                score
            )
            if hybrid:
                weight = vector_weight if branch == "vector" else 1 - vector_weight
                item["fusion_score"] = (item["fusion_score"] or 0) + weight / (
                    60 + rank
                )
    if hybrid:
        ordered = sorted(
            candidates.items(), key=lambda pair: (-pair[1]["fusion_score"], pair[0])
        )
    else:
        ordered = sorted(
            candidates.items(), key=lambda pair: pair[1][f"{settings.mode}_rank"]
        )
    items = [
        dict(item, rank=rank)
        for rank, (_, item) in enumerate(ordered[: settings.top_k], 1)
    ]
    diagnostics.update(candidate_count=len(candidates), output_count=len(items))
    return items, diagnostics
