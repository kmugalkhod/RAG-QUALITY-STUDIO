"""Website revision persistence and exact immutable-index preparation."""

import hashlib
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.connectors.website import WebsiteArtifact
from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
    chunker_version_for_node,
    processing_identity,
)
from app.ingestion_content.contracts import ExtractedDocumentV1
from app.models.document import ProcessingRun
from app.models.source import SourceRevision, WebsiteRunItem
from app.pipelines.parsing import MAX_CHUNKS, ProcessingError
from app.pipelines.web_content import (
    CLEANER_VERSION,
    EXTRACTOR_VERSION,
    chunk_sections,
    extract_canonical_sections,
    extract_raw_sections,
    extract_sections,
)
from app.services.source_artifacts import (
    PreparedArtifact,
    SourceArtifactSpec,
    config_hash,
    persist_source_artifact,
)
from app.workers.processing import now


def _display_name(url: str) -> str:
    parts = urlsplit(url)
    tail = Path(parts.path).name or parts.hostname or "website"
    return tail[:255]


def canonical_extracted_document(
    artifact: WebsiteArtifact, clean
) -> ExtractedDocumentV1:
    structured = getattr(clean, "profile", None) == "structure-aware-v1"
    sections = (
        extract_canonical_sections(artifact.content)
        if structured
        else extract_raw_sections(
            artifact.content,
            preserve_whitespace=not clean.normalize_whitespace,
        )
    )
    return build_extracted_document(
        [
            CanonicalInputSegment(
                text=section.text,
                block_type=section.block_type,
                heading_path=section.path,
                provider="website",
                external_id=f"{artifact.canonical_location}#section-{ordinal}",
                attributes=section.attributes,
            )
            for ordinal, section in enumerate(sections)
        ],
        media_type=artifact.media_type,
        title=_display_name(artifact.canonical_location),
    )


def _canonical_chunks(
    artifact: WebsiteArtifact,
    chunk,
    clean,
    processing_config_hash,
    phase_callback=None,
    extracted: ExtractedDocumentV1 | None = None,
    repeated_site_fingerprints: set[str] | None = None,
):
    if phase_callback is not None:
        phase_callback("extract")
    extracted = extracted or canonical_extracted_document(artifact, clean)
    if phase_callback is not None:
        phase_callback("clean")
    cleaner = cleaner_for_node(clean)
    cleaned = clean_document(
        extracted,
        clean,
        cleaner,
        extractor_version=EXTRACTOR_VERSION,
        configuration_hash=processing_config_hash,
        repeated_site_fingerprints=repeated_site_fingerprints,
    )
    combined = "\n\n".join(block.text for block in cleaned.blocks)
    violation = cleaner.length_violation(len(combined), clean)
    if violation == "too_short":
        raise ProcessingError("Website page contains too little extractable main text.")
    if violation == "too_long":
        raise ProcessingError("Website page exceeds the configured cleaned-text limit.")
    if phase_callback is not None:
        phase_callback("chunk")
    result = chunk_cleaned_document(
        cleaned,
        chunk,
        provenance={"canonical_location": artifact.canonical_location},
        join_blocks=True,
    )
    if not result.chunks:
        raise ProcessingError("Website page contains no chunkable text.")
    if len(result.chunks) > MAX_CHUNKS:
        raise ProcessingError(
            "Website page exceeds the 50,000 chunk limit. Increase chunk size."
        )
    if sum(len(item.text) for item in result.chunks) > 10_000_000:
        raise ProcessingError("Website page exceeds the chunk-output limit.")
    records = []
    for prepared in result.chunks:
        paths = [
            cleaned.blocks[span.block_ordinal].heading_path
            for span in result.spans[prepared.ordinal]
        ]
        prefix = list(paths[0]) if paths else []
        for path in paths[1:]:
            prefix = [
                value
                for index, value in enumerate(prefix)
                if index < len(path) and path[index] == value
            ]
        record = prepared.as_record()
        record["provenance"] = {
            **record["provenance"],
            "section_path": prefix,
        }
        records.append(record)
    return PreparedArtifact(
        chunks=records,
        extracted_hash=hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        extracted=extracted,
        cleaned=cleaned,
        spans=result.spans,
        extractor_version=EXTRACTOR_VERSION,
    )


def persist_artifact(
    session: Session,
    project_id,
    artifact: WebsiteArtifact,
    chunk,
    clean,
    prior_revision: SourceRevision | None,
    phase_callback=None,
    extract=None,
    extracted: ExtractedDocumentV1 | None = None,
    repeated_site_fingerprints: set[str] | None = None,
):
    content_hash = hashlib.sha256(artifact.content).hexdigest()
    cleaner = cleaner_for_node(clean)
    if getattr(clean, "profile", None) is None:
        processing_config = {
            "extractor": EXTRACTOR_VERSION,
            "cleaner": CLEANER_VERSION,
            "clean": clean.model_dump(mode="json"),
            "chunk": chunk.model_dump(mode="json"),
        }
        processing_config_hash = config_hash(processing_config)
        parser_version = f"{EXTRACTOR_VERSION}/{CLEANER_VERSION}"
    else:
        processing_config, processing_config_hash = processing_identity(
            schema_version=2,
            extractor_version=EXTRACTOR_VERSION,
            cleaner_version=cleaner.version,
            chunker_version=chunker_version_for_node(chunk),
            extract={
                "strategy": "html_main",
                "pipeline": (
                    extract.model_dump(mode="json", exclude={"id", "type"})
                    if extract is not None
                    else None
                ),
            },
            clean=clean.model_dump(mode="json", exclude={"id", "type"}),
            chunk=chunk.model_dump(mode="json", exclude={"id", "type"}),
        )
        parser_version = f"{EXTRACTOR_VERSION}/{cleaner.version}"

    def prepare(_stored_path):
        if getattr(clean, "profile", None) is not None:
            return _canonical_chunks(
                artifact,
                chunk,
                clean,
                processing_config_hash,
                phase_callback,
                extracted,
                repeated_site_fingerprints,
            )
        if phase_callback is not None:
            phase_callback("extract")
        sections = extract_sections(artifact.content, clean, phase_callback)
        extracted_hash = hashlib.sha256(
            "\n\n".join(section.text for section in sections).encode("utf-8")
        ).hexdigest()
        if phase_callback is not None:
            phase_callback("chunk")
        return chunk_sections(sections, chunk.size, chunk.overlap), extracted_hash

    return persist_source_artifact(
        session,
        project_id,
        SourceArtifactSpec(
            kind="website",
            identity=artifact.canonical_location,
            external_id=artifact.canonical_location,
            canonical_location=artifact.canonical_location,
            content=artifact.content,
            content_hash=content_hash,
            filename=_display_name(artifact.canonical_location),
            document_media_type="text/html",
            revision_media_type=artifact.media_type,
            processing_config=processing_config,
            processing_config_hash=processing_config_hash,
            parser_version=parser_version,
            chunk_size=chunk.size,
            chunk_overlap=chunk.overlap,
            chunk_config_version=chunk.config_version,
            fetched_at=now(),
            etag=artifact.etag,
            last_modified=artifact.last_modified,
            provider_revision=artifact.etag or artifact.last_modified,
            provenance={
                "connector_kind": "website",
                "connector_version": "1",
                "canonical_location": artifact.canonical_location,
                "depth": artifact.depth,
            },
        ),
        prior_revision,
        prepare,
        reuse_stage=phase_callback,
    )


def add_run_item(
    session,
    *,
    run,
    ordinal,
    source_node_id,
    outcome,
    reason,
    location=None,
    display_name=None,
    media_type=None,
    source_item=None,
    revision=None,
    error=None,
):
    item = WebsiteRunItem(
        run_id=run.id,
        ordinal=ordinal,
        project_id=run.project_id,
        source_node_id=source_node_id,
        source_item_id=source_item.id if source_item else None,
        source_revision_id=revision.id if revision else None,
        canonical_location=location,
        display_name=(display_name or location or "Undiscovered website item")[:500],
        media_type=media_type,
        outcome=outcome,
        status="failed" if outcome == "failed" else "ready",
        reason=reason[:500],
        chunk_count=(
            session.get(ProcessingRun, revision.processing_run_id).chunk_count
            if revision
            else 0
        ),
        error=error,
        updated_at=now(),
    )
    session.add(item)
    return item


def require_artifacts(artifacts):
    if not artifacts:
        raise HTTPException(409, "Website discovery found no indexable HTML pages.")
