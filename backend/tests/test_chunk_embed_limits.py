"""Spec 0012 Slice 2: passages always fit the embedding provider's input limit."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.ingestion_content import (
    CanonicalInputSegment,
    IngestionStageError,
    build_extracted_document,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.chunking import EMBEDDING_INPUT_BYTES, HEADING_PREFIX_BYTES
from app.ingestion_content.cleaning import default_structure_steps
from app.schemas.ingestion import (
    CharacterChunkNodeV2,
    CleanNodeV2,
    SectionTokenChunkNodeV2,
)

HEADING = "Harbour records" + " and lantern ledgers" * 24  # about 500 bytes


def _cleaned(segments):
    node = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=deepcopy(default_structure_steps()),
    )
    extracted = build_extracted_document(segments, media_type="text/plain")
    return clean_document(
        extracted,
        node,
        cleaner_for_node(node),
        extractor_version="test",
        configuration_hash="0" * 64,
    )


def _with_heading(body: str):
    return _cleaned(
        [
            CanonicalInputSegment(text=HEADING, page_number=1, block_type="heading"),
            CanonicalInputSegment(
                text=body,
                page_number=1,
                block_type="paragraph",
                heading_path=(HEADING,),
            ),
        ]
    )


@pytest.mark.parametrize("version", ["section-token-v1", "section-token-v2"])
def test_a_long_heading_is_kept_whole_when_the_passage_fits(version):
    cleaned = _with_heading("The archive keeps lanterns. " * 10)
    chunk = SectionTokenChunkNodeV2(
        id="chunk", type="chunk", algorithm="section_token", config_version=version
    )
    result = chunk_cleaned_document(cleaned, chunk)
    heading = HEADING.strip()
    for value in result.chunks:
        assert value.provenance["embedding_prefix"] == f"Section: {heading}\n\n"
        assert len(value.provenance["embedding_prefix"].encode()) > HEADING_PREFIX_BYTES


@pytest.mark.parametrize("version", ["section-token-v1", "section-token-v2"])
def test_a_long_heading_is_shortened_only_where_the_passage_would_not_embed(version):
    body = ("The archive keeps lanterns, maps and letters. " * 200)[:7850]
    cleaned = _with_heading(body)
    chunk = SectionTokenChunkNodeV2(
        id="chunk",
        type="chunk",
        algorithm="section_token",
        target_tokens=7800,
        maximum_tokens=7891,
        overlap_tokens=80,
        config_version=version,
    )
    result = chunk_cleaned_document(cleaned, chunk)
    passage = next(
        value for value in result.chunks if value.text.startswith("The archive")
    )
    prefix = passage.provenance["embedding_prefix"]
    assert len(prefix.encode()) <= HEADING_PREFIX_BYTES
    assert prefix.startswith("Section: …") and prefix.endswith("ledgers\n\n")
    assert passage.embedding_text == prefix + passage.text
    assert len(passage.embedding_text.encode()) <= EMBEDDING_INPUT_BYTES


def test_a_passage_too_large_to_embed_stops_the_chunk_stage():
    cleaned = _cleaned(
        [CanonicalInputSegment(text="€" * 6000, page_number=3, block_type="paragraph")]
    )
    chunk = CharacterChunkNodeV2(
        id="chunk", type="chunk", algorithm="character_window", size=5000, overlap=0
    )
    with pytest.raises(IngestionStageError) as raised:
        chunk_cleaned_document(cleaned, chunk)
    assert raised.value.stage == "chunk"
    assert raised.value.code == "passage_too_large"
    assert raised.value.message.startswith(
        "Passage 1 on page 3 is 15,000 bytes with its heading"
    )
