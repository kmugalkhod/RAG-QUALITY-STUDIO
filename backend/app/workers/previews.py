"""Fenced execution of bounded source and processing-preview jobs."""

import hashlib
import json
import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.artifact_crypto import ArtifactKeyring
from app.core.config import settings
from app.connectors.base import ConnectorFailure
from app.connectors.website import WebsiteConnector
from app.connectors.s3 import S3Connector
from app.connectors.notion import NotionConnector
from app.connectors.confluence import ConfluenceConnector
from app.db.session import engine
from app.ingestion_content import (
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.extractors import extract_document
from app.ingestion_content.quality import quality_policy_settings
from app.ingestion_content.duplicates import DuplicateCandidate, classify_duplicates
from app.models.document import Document
from app.models.preview import (
    SourcePreview,
    SourcePreviewItem,
    SourcePreviewRepresentation,
)
from app.schemas.ingestion import IngestionExecution
from app.services import (
    confluence_ingestion,
    connections,
    ingestion,
    notion_ingestion,
    s3_ingestion,
    website_ingestion,
)
from app.services import artifact_storage
from app.services.source_artifacts import PreparedArtifact
from app.workers.celery_app import celery
from app.workers.processing import now


MAX_PREVIEW_REPRESENTATIONS_PER_STAGE = 1_000
MAX_PREVIEW_TEXT_PER_REPRESENTATION = 50_000
MAX_PREVIEW_TOTAL_TEXT = 2_000_000


def _outcomes(db_session, project_id, execution):
    results = []
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    extract = next(node for node in execution.nodes if node.type == "extract")
    for source in [node for node in execution.nodes if node.type == "source"]:
        if source.config.kind == "existing_files":
            existing_execution = execution.model_copy(
                update={
                    "nodes": [
                        node
                        for node in execution.nodes
                        if node.type != "source" or node.id == source.id
                    ],
                    "edges": [
                        edge
                        for edge in execution.edges
                        if edge.source == source.id
                        or edge.source
                        not in {
                            node.id for node in execution.nodes if node.type == "source"
                        }
                    ],
                }
            )
            for item in ingestion.preview(
                db_session, project_id, existing_execution
            ).items:
                results.append(
                    dict(
                        source_node_id=source.id,
                        external_id=str(item.document_id),
                        display_name=item.filename,
                        canonical_location=f"project-file:{item.document_id}",
                        provider_revision=item.content_hash,
                        media_type=item.media_type,
                        status="included" if item.included else "excluded",
                        reason=item.reason,
                        size_bytes=item.size_bytes,
                        depth=None,
                        error_code=None,
                        _document_id=item.document_id,
                        _fetch_mode="cached-artifact",
                        _kind="existing_files",
                    )
                )
        elif source.config.kind == "website":
            outcomes, artifacts = WebsiteConnector().fetch_all(source.config, {})
            by_location = {item.canonical_location: item for item in artifacts}
            for item in outcomes:
                results.append(
                    dict(
                        source_node_id=source.id,
                        **item.__dict__,
                        _artifact=by_location.get(item.canonical_location),
                        _fetch_mode="network",
                        _kind="website",
                    )
                )
        elif source.config.kind == "s3":
            credentials = connections.credentials_for_use(
                db_session,
                project_id,
                source.config.connection_id,
                "s3",
            )
            _, processing_hash = s3_ingestion.processing_configuration(
                chunk, clean, extract
            )
            outcomes, artifacts = S3Connector(credentials).fetch_all(
                source.config, {}, processing_hash
            )
            by_location = {item.item.canonical_location: item for item in artifacts}
            for item in outcomes:
                results.append(
                    dict(
                        source_node_id=source.id,
                        **item.__dict__,
                        _artifact=by_location.get(item.canonical_location),
                        _fetch_mode="network",
                        _kind="s3",
                    )
                )
        elif source.config.kind == "notion":
            credentials = connections.credentials_for_use(
                db_session,
                project_id,
                source.config.connection_id,
                "notion",
            )
            _, processing_hash = notion_ingestion.processing_configuration(
                chunk, clean, extract
            )
            outcomes, artifacts = NotionConnector(credentials).fetch_all(
                source.config, {}, processing_hash
            )
            by_location = {item.item.canonical_location: item for item in artifacts}
            for item in outcomes:
                results.append(
                    dict(
                        source_node_id=source.id,
                        **item.__dict__,
                        _artifact=by_location.get(item.canonical_location),
                        _fetch_mode="network",
                        _kind="notion",
                    )
                )
        else:
            credentials = connections.credentials_for_use(
                db_session, project_id, source.config.connection_id, "confluence"
            )
            _, processing_hash = confluence_ingestion.processing_configuration(
                chunk, clean, extract
            )
            outcomes, artifacts = ConfluenceConnector(credentials).fetch_all(
                source.config, {}, processing_hash
            )
            by_location = {item.item.canonical_location: item for item in artifacts}
            for item in outcomes:
                results.append(
                    dict(
                        source_node_id=source.id,
                        **item.__dict__,
                        _artifact=by_location.get(item.canonical_location),
                        _fetch_mode="network",
                        _kind="confluence",
                    )
                )
    return results


def _bounded_text(value: str, budget: list[int]) -> tuple[str, bool]:
    remaining = max(0, MAX_PREVIEW_TOTAL_TEXT - budget[0])
    limit = min(MAX_PREVIEW_TEXT_PER_REPRESENTATION, remaining)
    result = value[:limit]
    budget[0] += len(result)
    return result, len(result) < len(value)


def _path_prepared(path, media_type, title, extract, clean, chunk, config_hash):
    extracted, extractor_version = extract_document(path, media_type, title, extract)
    cleaner = cleaner_for_node(clean)
    cleaned = clean_document(
        extracted,
        clean,
        cleaner,
        extractor_version=extractor_version,
        configuration_hash=config_hash,
    )
    chunking = chunk_cleaned_document(cleaned, chunk)
    return PreparedArtifact(
        chunks=[item.as_record() for item in chunking.chunks],
        extracted_hash=hashlib.sha256(
            "\n\n".join(block.text for block in cleaned.blocks).encode("utf-8")
        ).hexdigest(),
        extracted=extracted,
        cleaned=cleaned,
        spans=chunking.spans,
        extractor_version=extractor_version,
    )


def _prepare_item(session, item, execution, config_hash):
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    extract = next(node for node in execution.nodes if node.type == "extract")
    kind = item.get("_kind")
    if kind == "existing_files":
        document = session.get(Document, item["_document_id"])
        if document is None:
            raise ValueError("The selected project file is unavailable.")
        raw = artifact_storage.read(document)
        with artifact_storage.temporary_plaintext(raw) as path:
            prepared = _path_prepared(
                path,
                document.media_type,
                document.filename,
                extract,
                clean,
                chunk,
                config_hash,
            )
        return prepared, raw
    artifact = item.get("_artifact")
    if artifact is None:
        return None, None
    if kind == "website":
        return (
            website_ingestion.prepare_preview_artifact(
                artifact, chunk, clean, extract, config_hash
            ),
            artifact.content,
        )
    if kind == "notion":
        return (
            notion_ingestion.prepare_preview_artifact(
                artifact, chunk, clean, extract, config_hash
            ),
            artifact.content,
        )
    if kind == "confluence":
        return (
            confluence_ingestion.prepare_preview_artifact(
                artifact, chunk, clean, extract, config_hash
            ),
            artifact.content,
        )
    if artifact.content is None:
        return None, None
    with tempfile.TemporaryDirectory(prefix="rqs-preview-") as directory:
        path = Path(directory) / "artifact"
        path.write_bytes(artifact.content)
        prepared = s3_ingestion.prepare_preview_artifact(
            path,
            artifact.item.media_type,
            artifact.item.external_id,
            artifact.item.display_name,
            chunk,
            clean,
            extract,
            config_hash,
        )
    return prepared, artifact.content


def _representations(prepared, raw, media_type):
    budget = [0]
    rows = []

    def add(stage, ordinal, block_type, value, metadata):
        if ordinal >= MAX_PREVIEW_REPRESENTATIONS_PER_STAGE:
            return
        text, truncated = _bounded_text(value, budget)
        rows.append(
            {
                "stage": stage,
                "ordinal": ordinal,
                "block_type": block_type,
                "text": text,
                "metadata_json": {**metadata, "text_truncated": truncated},
            }
        )

    raw_text = ""
    if raw is not None and media_type and media_type.startswith("text/"):
        raw_text = raw.decode("utf-8", errors="replace")
    add(
        "raw",
        0,
        "artifact",
        raw_text,
        {"media_type": media_type, "size_bytes": len(raw or b"")},
    )
    for block in prepared.extracted.blocks:
        add(
            "extracted",
            block.ordinal,
            block.type,
            block.text,
            {
                "block_id": block.id,
                "page_number": block.page_number,
                "heading_path": block.heading_path,
                "source_span": block.source_span.model_dump(mode="json"),
            },
        )
    for block in prepared.cleaned.blocks:
        add(
            "cleaned",
            block.ordinal,
            block.type,
            block.text,
            {
                "block_id": block.id,
                "page_number": block.page_number,
                "heading_path": block.heading_path,
                "source_span": block.source_span.model_dump(mode="json"),
            },
        )
    cleaned_by_parent = {}
    for block in prepared.cleaned.blocks:
        parent_ids = (
            block.source_span.parent_block_ids
            if block.source_span.kind == "derived"
            else [block.id]
        )
        for block_id in parent_ids:
            cleaned_by_parent.setdefault(block_id, []).append(block)
    for block in prepared.extracted.blocks:
        after = cleaned_by_parent.get(block.id, [])
        after_text = "\n\n".join(value.text for value in after)
        add(
            "diff",
            block.ordinal,
            block.type,
            after_text,
            {
                "block_id": block.id,
                "before_text": block.text[:MAX_PREVIEW_TEXT_PER_REPRESENTATION],
                "action": (
                    "removed"
                    if not after
                    else "unchanged"
                    if after_text == block.text
                    else "rewritten"
                ),
            },
        )
    for chunk in prepared.chunks:
        embedding_text = chunk.get("embedding_text") or chunk["text"]
        prefix = (
            embedding_text[: -len(chunk["text"])].rstrip()
            if embedding_text.endswith(chunk["text"])
            else ""
        )
        add(
            "chunks",
            chunk["ordinal"],
            chunk.get("chunk_role") or "leaf",
            chunk["text"],
            {
                "page_number": chunk.get("page_number"),
                "start_char": chunk.get("start_char"),
                "end_char": chunk.get("end_char"),
                "token_count": chunk.get("token_count"),
                "embedding_token_count": chunk.get("embedding_token_count"),
                "embedding_prefix": prefix,
                "parent_ordinal": chunk.get("parent_ordinal"),
                "findings": chunk.get("findings") or [],
                "spans": [
                    span.model_dump(mode="json")
                    for span in prepared.spans.get(chunk["ordinal"], [])
                ],
            },
        )
    return rows


def _process_outcomes(session, outcomes, execution, config_hash):
    quality_counts = {value: 0 for value in ("pass", "warn", "exclude", "fail")}
    representations = []
    known_compute_ms = 0
    extract_node = next(node for node in execution.nodes if node.type == "extract")
    clean_node = next(node for node in execution.nodes if node.type == "clean")
    source_kinds = {
        node.id: node.config.kind for node in execution.nodes if node.type == "source"
    }
    policy = getattr(extract_node, "quality_policy", "default-v1")
    policy_settings = quality_policy_settings(policy)
    for ordinal, item in enumerate(outcomes):
        item["fetch_mode"] = item.get("_fetch_mode", "network")
        item["processing_config_hash"] = config_hash
        item["findings"] = []
        item["metrics"] = {}
        item["stage_timings"] = {}
        item["cost_basis"] = {
            "currency": "USD",
            "known_monetary_cost": None,
            "local_compute_measurement": "duration_ms",
        }
        if item["status"] != "included":
            item["processing_status"] = "skipped"
            item["quality_decision"] = None
            continue
        if execution.schema_version == 1:
            item["processing_status"] = "skipped"
            item["quality_decision"] = None
            item["reason"] = (
                f"{item['reason']} Legacy v1 previews source selection only."
            )
            continue
        started = time.perf_counter()
        try:
            prepared, raw = _prepare_item(session, item, execution, config_hash)
            if prepared is None:
                item["processing_status"] = "skipped"
                item["quality_decision"] = None
                item["reason"] = (
                    "Source discovery succeeded, but no immutable or fetched artifact "
                    "was available for processing preview."
                )
                continue
            decision = prepared.extracted.measurements.quality_decision
            elapsed = int((time.perf_counter() - started) * 1000)
            extraction_ms = prepared.extracted.measurements.extraction_duration_ms
            cleaning_ms = sum(
                value.duration_ms for value in prepared.cleaned.transforms
            )
            item["quality_decision"] = decision
            item["processing_status"] = "succeeded"
            item["findings"] = [
                value.model_dump(mode="json")
                for value in prepared.extracted.findings[:100]
            ] + [
                value.model_dump(mode="json")
                for value in prepared.cleaned.sensitive_findings[:100]
            ]
            item["metrics"] = {
                **prepared.extracted.measurements.model_dump(mode="json"),
                "language": (
                    prepared.extracted.language.model_dump(mode="json")
                    if prepared.extracted.language
                    else None
                ),
                "cleaned_character_count": prepared.cleaned.measurements.character_count,
                "chunk_count": len(prepared.chunks),
                "warning_publication": policy_settings["warning_action"],
            }
            item["stage_timings"] = {
                "extract_ms": extraction_ms,
                "clean_ms": cleaning_ms,
                "chunk_ms": max(0, elapsed - extraction_ms - cleaning_ms),
                "total_ms": elapsed,
            }
            known_compute_ms += elapsed
            quality_counts[decision] += 1
            identity = (
                item.get("canonical_location")
                or item.get("external_id")
                or item.get("display_name")
            )
            raw_bytes = raw or "\n".join(
                block.text for block in prepared.extracted.blocks
            ).encode("utf-8")
            item["_duplicate_candidate"] = DuplicateCandidate(
                identity=identity,
                source_kind=source_kinds.get(item["source_node_id"], "existing_files"),
                raw_hash=hashlib.sha256(raw_bytes).hexdigest(),
                cleaned_hash=prepared.cleaned.output_hash,
                text="\n".join(block.text for block in prepared.cleaned.blocks),
                stable_order=ordinal,
            )
            item["_quality_for_duplicate"] = decision
            for row in _representations(prepared, raw, item.get("media_type")):
                representations.append(
                    {
                        "preview_id": None,
                        "item_ordinal": ordinal,
                        **row,
                    }
                )
        except Exception:
            # Preview item errors are safe and item-scoped; raw source text is never echoed.
            item["processing_status"] = "failed"
            item["quality_decision"] = "fail"
            item["error_code"] = "processing_preview_failed"
            item["reason"] = "The exact processing preview could not be completed."
            quality_counts["fail"] += 1
    if execution.schema_version == 2:
        candidates = [
            item["_duplicate_candidate"]
            for item in outcomes
            if item.get("_duplicate_candidate") is not None
        ]
        decisions = classify_duplicates(candidates, clean_node.duplicate_policy)
        for item in outcomes:
            candidate = item.pop("_duplicate_candidate", None)
            decision = item.pop("_quality_for_duplicate", None)
            if candidate is None:
                continue
            duplicate = decisions[candidate.identity]
            item["duplicate_decision"] = duplicate.as_dict()
            if duplicate.outcome == "excluded":
                item["status"] = "duplicate"
                item["reason"] = (
                    f"Duplicate of {duplicate.retained_identity} by "
                    f"{duplicate.method} ({duplicate.similarity:.3f})."
                )
                if decision:
                    quality_counts[decision] -= 1
    return quality_counts, known_compute_ms, representations


def process_preview(preview_id: UUID, db_engine=engine, connector_factory=None):
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid4()
    with Session(db_engine) as session:
        preview = session.scalar(
            select(SourcePreview)
            .where(SourcePreview.id == preview_id)
            .with_for_update()
        )
        if preview is None or preview.status != "queued" or preview.failures >= 3:
            return
        preview.status = "running"
        preview.progress = 5
        preview.attempts += 1
        preview.execution_token = token
        preview.started_at = preview.started_at or now()
        preview.updated_at = now()
        preview.error = None
        execution = IngestionExecution.model_validate(preview.execution)
        project_id = preview.project_id
        configuration_hash = preview.configuration_hash
        session.commit()
    try:
        with Session(db_engine) as session:
            if connector_factory is None:
                outcomes = _outcomes(session, project_id, execution)
            else:
                outcomes = connector_factory(session, project_id, execution)
            quality_counts, known_compute_ms, representations = _process_outcomes(
                session, outcomes, execution, configuration_hash
            )
        counts = {kind: 0 for kind in ("included", "excluded", "duplicate", "failed")}
        for item in outcomes:
            counts[item["status"]] += 1
        with Session(db_engine) as session:
            preview = session.scalar(
                select(SourcePreview)
                .where(SourcePreview.id == preview_id)
                .with_for_update()
            )
            if (
                preview is None
                or preview.status != "running"
                or preview.execution_token != token
            ):
                return
            session.execute(
                delete(SourcePreviewItem).where(
                    SourcePreviewItem.preview_id == preview.id
                )
            )
            item_columns = {
                column.name
                for column in SourcePreviewItem.__table__.columns
                if column.name not in ("preview_id", "ordinal", "created_at")
            }
            for ordinal, item in enumerate(outcomes):
                session.add(
                    SourcePreviewItem(
                        preview_id=preview.id,
                        ordinal=ordinal,
                        **{
                            key: value
                            for key, value in item.items()
                            if key in item_columns
                        },
                    )
                )
            session.flush()
            if representations:
                if preview.protected_content:
                    keyring = ArtifactKeyring.from_settings(settings)
                    data_key = keyring.unwrap_object_key(
                        object_kind="source-preview",
                        wrapped_key=preview.protected_wrapped_key,
                        wrap_nonce=preview.protected_wrap_nonce,
                        key_version=preview.protected_key_version,
                        schema_version=preview.protected_schema,
                        project_id=preview.project_id,
                        object_id=preview.id,
                    )
                    for value in representations:
                        if value["stage"] not in {"raw", "extracted", "diff"}:
                            continue
                        context = (
                            f"{value['item_ordinal']}:{value['stage']}:"
                            f"{value['ordinal']}"
                        )
                        payload = json.dumps(
                            {
                                "text": value["text"],
                                "metadata": value.get("metadata_json", {}),
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ).encode("utf-8")
                        ciphertext, nonce = keyring.encrypt_object_payload(
                            data_key,
                            payload,
                            object_kind="source-preview",
                            project_id=preview.project_id,
                            object_id=preview.id,
                            context=context,
                        )
                        value["text"] = "[PROTECTED SOURCE CONTENT]"
                        value["metadata_json"] = {"protected": True}
                        value["protected_payload"] = ciphertext
                        value["protected_nonce"] = nonce
                session.execute(
                    insert(SourcePreviewRepresentation),
                    [{**value, "preview_id": preview.id} for value in representations],
                )
            preview.status = "succeeded"
            preview.progress = 100
            preview.discovered_count = len(outcomes)
            preview.included_count = counts["included"]
            preview.excluded_count = counts["excluded"]
            preview.duplicate_count = counts["duplicate"]
            preview.failed_count = counts["failed"]
            preview.pass_count = quality_counts["pass"]
            preview.warn_count = quality_counts["warn"]
            preview.exclude_count = quality_counts["exclude"]
            preview.quality_fail_count = quality_counts["fail"]
            preview.known_compute_ms = known_compute_ms
            modes = {
                item.get("fetch_mode", item.get("_fetch_mode", "network"))
                for item in outcomes
            }
            preview.fetch_mode = next(iter(modes)) if len(modes) == 1 else "mixed"
            preview.cost_basis = {
                **(preview.cost_basis or {}),
                "known_local_compute_ms": known_compute_ms,
            }
            preview.execution_token = None
            preview.failures = 0
            preview.error = None
            preview.updated_at = preview.finished_at = now()
            session.commit()
    except Exception as exc:
        retryable = isinstance(exc, SQLAlchemyError) or (
            isinstance(exc, ConnectorFailure) and exc.issue.retryable
        )
        safe_error = (
            exc.issue.message
            if isinstance(exc, ConnectorFailure)
            else "Source preview was interrupted. Retry from its durable job record."
        )
        with Session(db_engine) as session:
            preview = session.scalar(
                select(SourcePreview)
                .where(SourcePreview.id == preview_id)
                .with_for_update()
            )
            if (
                preview is None
                or preview.status != "running"
                or preview.execution_token != token
            ):
                return
            preview.failures += 1
            preview.execution_token = None
            preview.error = safe_error
            preview.updated_at = now()
            if retryable and preview.failures < 3:
                preview.status = "queued"
                preview.dispatched_at = None
            else:
                preview.status = "failed"
                preview.finished_at = now()
            session.commit()


@celery.task(name="preview.sources", soft_time_limit=3660, time_limit=3670)
def preview_sources(preview_id: str):
    process_preview(UUID(preview_id))
