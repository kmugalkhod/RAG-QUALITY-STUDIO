"""Strict application-owned canonical ingestion representations."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoundingBox(Strict):
    left: float = Field(ge=0, le=1, allow_inf_nan=False)
    top: float = Field(ge=0, le=1, allow_inf_nan=False)
    right: float = Field(ge=0, le=1, allow_inf_nan=False)
    bottom: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Bounding-box coordinates must define a positive area.")
        return self


class ArtifactTextSpan(Strict):
    kind: Literal["artifact_text"]
    page_number: int | None = Field(default=None, ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_char <= self.start_char:
            raise ValueError("Source-span end must be after its start.")
        return self


class ProviderBlockSpan(Strict):
    kind: Literal["provider_block"]
    provider: Literal["website", "notion", "confluence"]
    external_id: str = Field(min_length=1, max_length=1000)


class DerivedSourceSpan(Strict):
    kind: Literal["derived"]
    parent_block_ids: list[str] = Field(min_length=1, max_length=100)


SourceSpan = Annotated[
    ArtifactTextSpan | ProviderBlockSpan | DerivedSourceSpan,
    Field(discriminator="kind"),
]


BlockType = Literal[
    "title",
    "heading",
    "paragraph",
    "list_item",
    "table",
    "code",
    "quote",
    "image_caption",
    "footnote",
    "unknown",
]


class CanonicalBlock(Strict):
    id: str = Field(min_length=16, max_length=64, pattern=r"^[a-f0-9]+$")
    ordinal: int = Field(ge=0)
    type: BlockType
    text: str = Field(min_length=1, max_length=2_000_000)
    page_number: int | None = Field(default=None, ge=1)
    bounding_box: BoundingBox | None = None
    heading_path: list[str] = Field(default_factory=list, max_length=20)
    source_span: SourceSpan
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_metadata(self):
        if any(not value or len(value) > 500 for value in self.heading_path):
            raise ValueError("Heading-path values must contain 1 to 500 characters.")
        if any(not key or len(key) > 100 for key in self.attributes):
            raise ValueError("Attribute keys must contain 1 to 100 characters.")
        try:
            encoded = json.dumps(
                self.attributes,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("Block attributes must contain JSON values only.") from exc
        if len(encoded) > 16_384:
            raise ValueError("Block attributes exceed the 16 KiB limit.")
        return self


class ExtractedPage(Strict):
    page_number: int = Field(ge=1)
    block_ids: list[str] = Field(default_factory=list, max_length=10_000)
    origin: Literal["native", "layout", "ocr"] = "native"
    character_count: int = Field(default=0, ge=0)
    block_count: int = Field(default=0, ge=0)
    fallback_reason: str | None = Field(default=None, max_length=200)
    width_points: float | None = Field(
        default=None, gt=0, le=100_000, allow_inf_nan=False
    )
    height_points: float | None = Field(
        default=None, gt=0, le=100_000, allow_inf_nan=False
    )
    rotation_degrees: int = Field(default=0, ge=0, le=359)
    ocr_confidence: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False
    )


class LanguageResult(Strict):
    language: str = Field(min_length=2, max_length=35)
    method: str = Field(min_length=1, max_length=80)


class QualityFinding(Strict):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    severity: Literal["info", "warning", "error"]
    count: int = Field(default=1, ge=1, le=1_000_000)
    message: str = Field(min_length=1, max_length=500)
    page_numbers: list[int] = Field(default_factory=list, max_length=100)
    remediation: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def ordered_pages(self):
        if self.page_numbers != sorted(set(self.page_numbers)):
            raise ValueError("Finding page numbers must be unique and ordered.")
        return self


class DocumentMeasurements(Strict):
    character_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    empty_block_count: int = Field(default=0, ge=0)
    page_character_counts: list[int] = Field(default_factory=list, max_length=2_000)
    page_block_counts: list[int] = Field(default_factory=list, max_length=2_000)
    native_page_count: int = Field(default=0, ge=0)
    layout_page_count: int = Field(default=0, ge=0)
    ocr_page_count: int = Field(default=0, ge=0)
    empty_page_count: int = Field(default=0, ge=0)
    replacement_character_ratio: float = Field(
        default=0, ge=0, le=1, allow_inf_nan=False
    )
    control_character_ratio: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    repeated_line_ratio: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    suspicious_reading_order_count: int = Field(default=0, ge=0)
    table_count: int = Field(default=0, ge=0)
    malformed_table_count: int = Field(default=0, ge=0)
    ocr_confidence_median: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False
    )
    ocr_confidence_p05: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False
    )
    extraction_duration_ms: int = Field(default=0, ge=0)
    resource_category: Literal["native", "bounded-cpu"] = "native"
    fallback_path: list[str] = Field(default_factory=list, max_length=2_000)
    quality_decision: Literal["pass", "warn", "exclude", "fail"] = "pass"


class ExtractedDocumentV1(Strict):
    schema_version: Literal[1] = 1
    media_type: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=1000)
    language: LanguageResult | None = None
    pages: list[ExtractedPage] = Field(default_factory=list, max_length=100_000)
    blocks: list[CanonicalBlock] = Field(max_length=100_000)
    measurements: DocumentMeasurements
    findings: list[QualityFinding] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def coherent_order_and_pages(self):
        if [block.ordinal for block in self.blocks] != list(range(len(self.blocks))):
            raise ValueError("Block ordinals must be contiguous and ordered.")
        block_ids = [block.id for block in self.blocks]
        if len(set(block_ids)) != len(block_ids):
            raise ValueError("Block IDs must be unique within a derivation.")
        page_numbers = [page.page_number for page in self.pages]
        if page_numbers != sorted(set(page_numbers)):
            raise ValueError("Pages must be unique and ordered.")
        if any(
            block_id not in set(block_ids)
            for page in self.pages
            for block_id in page.block_ids
        ):
            raise ValueError("Every page block ID must reference this document.")
        if self.measurements.block_count != len(self.blocks):
            raise ValueError("Block measurement does not match the document.")
        if self.measurements.page_count != len(self.pages):
            raise ValueError("Page measurement does not match the document.")
        if self.measurements.page_character_counts and len(
            self.measurements.page_character_counts
        ) != len(self.pages):
            raise ValueError("Per-page character measurements must match the pages.")
        if self.measurements.page_block_counts and len(
            self.measurements.page_block_counts
        ) != len(self.pages):
            raise ValueError("Per-page block measurements must match the pages.")
        return self


class TransformChange(Strict):
    block_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-f0-9]+$")
    action: Literal["rewritten", "removed", "retained"]
    reason: str = Field(min_length=1, max_length=120)
    count: int = Field(default=1, ge=1, le=2_000_000)


class TransformAudit(Strict):
    transform: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)
    changed_blocks: int = Field(ge=0)
    removed_blocks: int = Field(ge=0)
    duration_ms: int = Field(default=0, ge=0)
    metrics: dict[str, int | float | str | bool] = Field(
        default_factory=dict, max_length=30
    )
    changes: list[TransformChange] = Field(default_factory=list, max_length=200)


class CleanedDocumentV1(Strict):
    schema_version: Literal[1] = 1
    media_type: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=1000)
    blocks: list[CanonicalBlock] = Field(max_length=100_000)
    extractor_version: str = Field(min_length=1, max_length=120)
    cleaner_version: str = Field(min_length=1, max_length=120)
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    transforms: list[TransformAudit] = Field(max_length=100)
    measurements: DocumentMeasurements
    findings: list[QualityFinding] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def coherent_order(self):
        if [block.ordinal for block in self.blocks] != list(range(len(self.blocks))):
            raise ValueError("Cleaned block ordinals must be contiguous and ordered.")
        if len({block.id for block in self.blocks}) != len(self.blocks):
            raise ValueError("Cleaned block IDs must be unique.")
        if self.measurements.block_count != len(self.blocks):
            raise ValueError("Block measurement does not match the cleaned document.")
        return self


class ChunkBlockSpanV1(Strict):
    block_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-f0-9]+$")
    block_ordinal: int = Field(ge=0)
    block_start_char: int = Field(ge=0)
    block_end_char: int = Field(gt=0)
    chunk_start_char: int = Field(ge=0)
    chunk_end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.block_end_char <= self.block_start_char:
            raise ValueError("Block-span end must be after its start.")
        if self.chunk_end_char <= self.chunk_start_char:
            raise ValueError("Chunk-span end must be after its start.")
        return self
