"""Application-owned ingestion processing contracts and current implementations."""

from app.ingestion_content.processing import (
    CHARACTER_CHUNKER_VERSION,
    LEGACY_CLEANER_VERSION,
    STANDARD_CLEANER_VERSION,
    STRUCTURE_CLEANER_VERSION,
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
from app.ingestion_content.canonical import (
    CanonicalChunkingResult,
    CanonicalInputSegment,
    build_extracted_document,
    chunk_cleaned_document,
    clean_document,
    document_hash,
)
from app.ingestion_content.contracts import (
    CanonicalBlock,
    ChunkBlockSpanV1,
    CleanedDocumentV1,
    ExtractedDocumentV1,
)

__all__ = [
    "CHARACTER_CHUNKER_VERSION",
    "LEGACY_CLEANER_VERSION",
    "STANDARD_CLEANER_VERSION",
    "STRUCTURE_CLEANER_VERSION",
    "CharacterWindowChunker",
    "CleanSemantics",
    "DeterministicCleaner",
    "ExtractedSegment",
    "IngestionStageError",
    "NativeTextExtractor",
    "PreparedChunk",
    "cleaner_for_node",
    "processing_identity",
    "CanonicalBlock",
    "CanonicalChunkingResult",
    "CanonicalInputSegment",
    "ChunkBlockSpanV1",
    "CleanedDocumentV1",
    "ExtractedDocumentV1",
    "build_extracted_document",
    "chunk_cleaned_document",
    "clean_document",
    "document_hash",
]
