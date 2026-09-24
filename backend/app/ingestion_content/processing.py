"""Versioned current-behavior extraction, cleaning and character chunking.

These contracts intentionally stop short of the canonical document IR introduced in
Phase 1. They give every Phase 0 connector one application-owned processing boundary
without inventing block or derivation persistence before those records are consumed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol

from app.pipelines.parsing import PARSER_VERSION, pages, windows


LEGACY_CLEANER_VERSION = "legacy-whitespace-boilerplate-v1"
STANDARD_CLEANER_VERSION = "deterministic-clean-v1"
STRUCTURE_CLEANER_VERSION = "structure-clean-v1"
CHARACTER_CHUNKER_VERSION = "character-window-v1"
_SPACE = re.compile(r"\s+")


class CleanSemantics(StrEnum):
    """Saved behavior, not a runtime guess.

    Legacy preserves schema-v1 output, including its historical final whitespace
    collapse when normalization was disabled. Standard makes `false` truthful: source
    whitespace is retained except where a configured literal is removed.
    """

    LEGACY_V1 = "legacy-v1"
    STANDARD_V1 = "standard-v1"


class IngestionStageError(Exception):
    """Safe typed error that can cross worker and API boundaries without raw text."""

    def __init__(
        self,
        stage: Literal["extract", "clean", "chunk"],
        code: str,
        message: str,
    ):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExtractedSegment:
    text: str
    page_number: int | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    completed: int = 1
    total: int = 1


@dataclass(frozen=True)
class PreparedChunk:
    ordinal: int
    page_number: int | None
    start_char: int
    end_char: int
    text: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "page_number": self.page_number,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "text": self.text,
            "provenance": self.provenance,
        }


class CleanSettings(Protocol):
    normalize_whitespace: bool
    repeated_boilerplate: list[str]
    minimum_text_chars: int
    maximum_text_chars: int


class ChunkSettings(Protocol):
    size: int
    overlap: int


class NativeTextExtractor:
    """Bounded TXT/PDF adapter over the existing parser contract."""

    version = PARSER_VERSION

    def extract(self, path: Path, media_type: str) -> Iterable[ExtractedSegment]:
        for page_number, text, completed, total in pages(path, media_type):
            yield ExtractedSegment(
                text=text,
                page_number=page_number,
                completed=completed,
                total=total,
            )


class DeterministicCleaner:
    def __init__(self, semantics: CleanSemantics):
        self.semantics = semantics
        self.version = (
            LEGACY_CLEANER_VERSION
            if semantics is CleanSemantics.LEGACY_V1
            else STANDARD_CLEANER_VERSION
        )

    def clean(self, text: str, settings: CleanSettings) -> str:
        value = text
        if settings.normalize_whitespace:
            value = _SPACE.sub(" ", value).strip()
        for repeated in settings.repeated_boilerplate:
            literal = repeated.strip()
            value = value.replace(
                literal,
                " " if self.semantics is CleanSemantics.LEGACY_V1 else "",
            )
        if self.semantics is CleanSemantics.LEGACY_V1:
            return _SPACE.sub(" ", value).strip()
        if settings.normalize_whitespace:
            return _SPACE.sub(" ", value).strip()
        return value

    @staticmethod
    def length_violation(
        text_length: int, settings: CleanSettings
    ) -> Literal["too_short", "too_long"] | None:
        if text_length < settings.minimum_text_chars:
            return "too_short"
        if text_length > settings.maximum_text_chars:
            return "too_long"
        return None


class StructureAwareCleaner:
    """Identity and shared bounds for the canonical ordered-transform engine."""

    version = STRUCTURE_CLEANER_VERSION

    @staticmethod
    def length_violation(
        text_length: int, settings: CleanSettings
    ) -> Literal["too_short", "too_long"] | None:
        return DeterministicCleaner.length_violation(text_length, settings)


class CharacterWindowChunker:
    version = CHARACTER_CHUNKER_VERSION

    def chunk_segment(
        self,
        segment: ExtractedSegment,
        settings: ChunkSettings,
        *,
        first_ordinal: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> list[PreparedChunk]:
        combined_provenance = {**segment.provenance, **(provenance or {})}
        return [
            PreparedChunk(
                ordinal=first_ordinal + offset,
                page_number=segment.page_number,
                start_char=start,
                end_char=end,
                text=text,
                provenance=combined_provenance,
            )
            for offset, (start, end, text) in enumerate(
                windows(segment.text, settings.size, settings.overlap)
            )
        ]


def cleaner_for_node(
    clean: CleanSettings,
) -> DeterministicCleaner | StructureAwareCleaner:
    if getattr(clean, "profile", None) == "structure-aware-v1":
        return StructureAwareCleaner()
    semantics = (
        CleanSemantics.STANDARD_V1
        if getattr(clean, "profile", None) == "standard-v1"
        else CleanSemantics.LEGACY_V1
    )
    return DeterministicCleaner(semantics)


def processing_identity(
    *,
    schema_version: int,
    extractor_version: str,
    cleaner_version: str,
    chunker_version: str,
    extract: dict[str, Any],
    clean: dict[str, Any],
    chunk: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Return canonical persisted configuration and its deterministic SHA-256."""

    value = {
        "schema_version": schema_version,
        "versions": {
            "extractor": extractor_version,
            "cleaner": cleaner_version,
            "chunker": chunker_version,
        },
        "extract": extract,
        "clean": clean,
        "chunk": chunk,
    }
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return value, hashlib.sha256(encoded).hexdigest()
