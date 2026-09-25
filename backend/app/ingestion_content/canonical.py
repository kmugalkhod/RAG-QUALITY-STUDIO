"""Deterministic construction of canonical extracted and cleaned documents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from app.ingestion_content.contracts import (
    ArtifactTextSpan,
    BoundingBox,
    CanonicalBlock,
    CleanedDocumentV1,
    ChunkBlockSpanV1,
    DocumentMeasurements,
    ExtractedDocumentV1,
    ExtractedPage,
    ProviderBlockSpan,
    QualityFinding,
    TransformAudit,
)
from app.ingestion_content.processing import (
    CharacterWindowChunker,
    DeterministicCleaner,
    ExtractedSegment,
    PreparedChunk,
)


@dataclass(frozen=True)
class CanonicalInputSegment:
    text: str
    page_number: int | None = None
    block_type: str = "unknown"
    heading_path: tuple[str, ...] = ()
    provider: str | None = None
    external_id: str | None = None
    attributes: dict[str, Any] | None = None
    bounding_box: BoundingBox | None = None


@dataclass(frozen=True)
class CanonicalChunkingResult:
    chunks: list[PreparedChunk]
    spans: dict[int, list[ChunkBlockSpanV1]]


def _hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def document_hash(blocks: Iterable[CanonicalBlock]) -> str:
    return _hash(
        [
            {
                "id": block.id,
                "ordinal": block.ordinal,
                "type": block.type,
                "text": block.text,
                "page_number": block.page_number,
                "heading_path": block.heading_path,
                "source_span": block.source_span.model_dump(mode="json"),
                "attributes": block.attributes,
            }
            for block in blocks
        ]
    )


def build_extracted_document(
    segments: Iterable[CanonicalInputSegment | ExtractedSegment],
    *,
    media_type: str,
    title: str | None = None,
    page_metadata: dict[int, dict[str, Any]] | None = None,
    findings: list[QualityFinding] | None = None,
    measurement_updates: dict[str, Any] | None = None,
) -> ExtractedDocumentV1:
    blocks = []
    page_cursor: dict[int | None, int] = {}
    for ordinal, segment in enumerate(segments):
        text = segment.text
        if not text:
            continue
        page_number = segment.page_number
        start = page_cursor.get(page_number, 0)
        end = start + len(text)
        page_cursor[page_number] = end
        provider = getattr(segment, "provider", None)
        external_id = getattr(segment, "external_id", None)
        source_span = (
            ProviderBlockSpan(
                kind="provider_block", provider=provider, external_id=external_id
            )
            if provider and external_id
            else ArtifactTextSpan(
                kind="artifact_text",
                page_number=page_number,
                start_char=start,
                end_char=end,
            )
        )
        block_type = getattr(segment, "block_type", "unknown")
        heading_path = list(getattr(segment, "heading_path", ()))
        attributes = dict(getattr(segment, "attributes", None) or {})
        block_id = _hash(
            {
                "ordinal": ordinal,
                "type": block_type,
                "page_number": page_number,
                "source_span": source_span.model_dump(mode="json"),
                "text": text,
            }
        )[:32]
        blocks.append(
            CanonicalBlock(
                id=block_id,
                ordinal=len(blocks),
                type=block_type,
                text=text,
                page_number=page_number,
                bounding_box=getattr(segment, "bounding_box", None),
                heading_path=heading_path,
                source_span=source_span,
                attributes=attributes,
            )
        )
    pages = [
        ExtractedPage(
            page_number=page_number,
            block_ids=[
                block.id for block in blocks if block.page_number == page_number
            ],
            **((page_metadata or {}).get(page_number, {})),
        )
        for page_number in sorted(
            set(page_metadata or {})
            | {block.page_number for block in blocks if block.page_number is not None}
        )
    ]
    measurements = DocumentMeasurements(
        character_count=sum(len(block.text) for block in blocks),
        block_count=len(blocks),
        page_count=len(pages),
        **(measurement_updates or {}),
    )
    return ExtractedDocumentV1(
        media_type=media_type,
        title=title,
        pages=pages,
        blocks=blocks,
        measurements=measurements,
        findings=findings or [],
    )


def clean_document(
    extracted: ExtractedDocumentV1,
    settings,
    cleaner: DeterministicCleaner,
    *,
    extractor_version: str,
    configuration_hash: str,
    repeated_site_fingerprints: set[str] | None = None,
) -> CleanedDocumentV1:
    if getattr(settings, "profile", None) == "structure-aware-v1":
        from app.ingestion_content.cleaning import clean_structure_document

        result = clean_structure_document(
            extracted,
            settings,
            extractor_version=extractor_version,
            configuration_hash=configuration_hash,
            repeated_site_fingerprints=repeated_site_fingerprints,
        )
    else:
        blocks = []
        seen: set[str] = set()
        changed = 0
        removed = 0
        for block in extracted.blocks:
            value = cleaner.clean(block.text, settings)
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
            duplicate = settings.exact_content_deduplication and digest in seen
            if not value or duplicate:
                removed += 1
                continue
            seen.add(digest)
            changed += value != block.text
            blocks.append(
                block.model_copy(update={"ordinal": len(blocks), "text": value})
            )
        output_hash = document_hash(blocks)
        result = CleanedDocumentV1(
            media_type=extracted.media_type,
            title=extracted.title,
            language=extracted.language,
            blocks=blocks,
            extractor_version=extractor_version,
            cleaner_version=cleaner.version,
            configuration_hash=configuration_hash,
            input_hash=document_hash(extracted.blocks),
            output_hash=output_hash,
            transforms=[
                TransformAudit(
                    transform="deterministic_clean",
                    version=cleaner.version,
                    changed_blocks=changed,
                    removed_blocks=removed,
                )
            ],
            measurements=extracted.measurements.model_copy(
                update={
                    "character_count": sum(len(block.text) for block in blocks),
                    "block_count": len(blocks),
                    "page_count": extracted.measurements.page_count,
                    "page_character_counts": [
                        sum(
                            len(block.text)
                            for block in blocks
                            if block.page_number == page.page_number
                        )
                        for page in extracted.pages
                    ],
                    "page_block_counts": [
                        sum(
                            1
                            for block in blocks
                            if block.page_number == page.page_number
                        )
                        for page in extracted.pages
                    ],
                }
            ),
            findings=extracted.findings,
        )
    policy = getattr(settings, "sensitive_data_policy", None)
    if policy is not None:
        from app.ingestion_content.sensitive_data import apply_sensitive_data_policy

        result, _ = apply_sensitive_data_policy(result, policy)
    return result


def chunk_cleaned_document(
    cleaned: CleanedDocumentV1,
    settings,
    *,
    provenance: dict[str, Any] | None = None,
    join_blocks: bool = False,
    separator: str = "\n\n",
) -> CanonicalChunkingResult:
    """Run the legacy character window algorithm over canonical cleaned blocks.

    Blocks stay independent so every emitted character has one exact, bounded source
    span. This is the historical behavior for native files and provider artifacts;
    connector-specific joins remain a legacy-v1 compatibility concern.
    """

    if getattr(settings, "algorithm", "character_window") != "character_window":
        from app.ingestion_content.chunking import chunk_structured_document

        chunks, spans = chunk_structured_document(
            cleaned,
            settings,
            provenance=provenance,
        )
        return CanonicalChunkingResult(chunks=chunks, spans=spans)

    chunker = CharacterWindowChunker()
    if join_blocks:
        combined = separator.join(block.text for block in cleaned.blocks)
        positions: list[tuple[CanonicalBlock, int, int]] = []
        cursor = 0
        for block in cleaned.blocks:
            positions.append((block, cursor, cursor + len(block.text)))
            cursor += len(block.text) + len(separator)
        prepared = chunker.chunk_segment(
            ExtractedSegment(text=combined, provenance=provenance or {}), settings
        )
        spans = {}
        for chunk in prepared:
            chunk_spans = []
            for block, block_left, block_right in positions:
                left = max(chunk.start_char, block_left)
                right = min(chunk.end_char, block_right)
                if left >= right:
                    continue
                chunk_spans.append(
                    ChunkBlockSpanV1(
                        block_id=block.id,
                        block_ordinal=block.ordinal,
                        block_start_char=left - block_left,
                        block_end_char=right - block_left,
                        chunk_start_char=left - chunk.start_char,
                        chunk_end_char=right - chunk.start_char,
                    )
                )
            spans[chunk.ordinal] = chunk_spans
        return CanonicalChunkingResult(chunks=prepared, spans=spans)

    chunks: list[PreparedChunk] = []
    spans: dict[int, list[ChunkBlockSpanV1]] = {}
    for block in cleaned.blocks:
        segment = ExtractedSegment(
            text=block.text,
            page_number=block.page_number,
            provenance={
                **(provenance or {}),
                "block_id": block.id,
                "block_type": block.type,
                "heading_path": block.heading_path,
            },
        )
        prepared = chunker.chunk_segment(
            segment,
            settings,
            first_ordinal=len(chunks),
        )
        for chunk in prepared:
            spans[chunk.ordinal] = [
                ChunkBlockSpanV1(
                    block_id=block.id,
                    block_ordinal=block.ordinal,
                    block_start_char=chunk.start_char,
                    block_end_char=chunk.end_char,
                    chunk_start_char=0,
                    chunk_end_char=len(chunk.text),
                )
            ]
        chunks.extend(prepared)
    return CanonicalChunkingResult(chunks=chunks, spans=spans)
