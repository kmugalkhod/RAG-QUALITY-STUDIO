"""Safe extraction capability discovery contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class ExtractionCapabilities(Strict):
    schema_version: Literal[1]
    media_types: list[Literal["application/pdf", "text/plain"]]
    profiles: list[ExtractionProfileCapability]
    ocr: OcrCapability
    table_modes: list[Literal["preserve", "markdown", "plain_text"]]
    quality_policies: list[Literal["default-v1", "strict-v1", "warn-v1"]]
