"""Safe extraction capability discovery contracts."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.ingestion import CleaningTransform, QualityPolicyV1


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractionProfileCapability(Strict):
    id: Literal["auto", "native", "layout_aware"]
    available: bool
    reason: str | None


class OcrCapability(Strict):
    available: bool
    languages: list[str]
    reason: str | None
    max_pages: int
    max_pixels_per_page: int


class CleaningProfileCapability(Strict):
    id: Literal["structure-aware-v1"]
    name: str
    config_version: Literal["structure-clean-v1"]
    steps: list[CleaningTransform]


class TokenizerCapability(Strict):
    id: Literal["utf8_byte"]
    version: Literal["utf8-byte-v1"]
    unit: str


class ChunkingProfileCapability(Strict):
    id: Literal["character_window", "section_token", "parent_child"]
    name: str
    description: str
    recommended: bool
    settings: dict[str, Any]


class QualityPolicyCapability(Strict):
    id: Literal["default-v1", "strict-v1", "warn-v1"]
    name: str
    description: str
    settings: QualityPolicyV1


class ExtractionCapabilities(Strict):
    schema_version: Literal[1]
    media_types: list[Literal["application/pdf", "text/plain"]]
    profiles: list[ExtractionProfileCapability]
    ocr: OcrCapability
    table_modes: list[Literal["preserve", "markdown", "plain_text"]]
    quality_policies: list[QualityPolicyCapability]
    cleaning_profiles: list[CleaningProfileCapability]
    tokenizers: list[TokenizerCapability]
    chunking_profiles: list[ChunkingProfileCapability]
