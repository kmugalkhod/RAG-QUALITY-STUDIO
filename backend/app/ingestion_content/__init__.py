"""Application-owned ingestion processing contracts and current implementations."""

from app.ingestion_content.processing import (
    CHARACTER_CHUNKER_VERSION,
    LEGACY_CLEANER_VERSION,
    STANDARD_CLEANER_VERSION,
    CharacterWindowChunker,
    CleanSemantics,
    DeterministicCleaner,
    ExtractedSegment,
    IngestionStageError,
    NativeTextExtractor,
    PreparedChunk,
    cleaner_for_node,
    processing_identity,
)

__all__ = [
    "CHARACTER_CHUNKER_VERSION",
    "LEGACY_CLEANER_VERSION",
    "STANDARD_CLEANER_VERSION",
    "CharacterWindowChunker",
    "CleanSemantics",
    "DeterministicCleaner",
    "ExtractedSegment",
    "IngestionStageError",
    "NativeTextExtractor",
    "PreparedChunk",
    "cleaner_for_node",
    "processing_identity",
]
