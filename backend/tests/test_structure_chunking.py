from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import default_structure_steps
from app.ingestion_content.tokenizers import tokenizer_for
from app.schemas.ingestion import (
    CleanNodeV2,
    ParentChildChunkNodeV2,
    SectionTokenChunkNodeV2,
)


def _cleaned(segments):
    extracted = build_extracted_document(segments, media_type="text/plain")
    clean = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=deepcopy(default_structure_steps()),
    )
    return clean_document(
        extracted,
        clean,
        cleaner_for_node(clean),
        extractor_version="test-extractor-v1",
        configuration_hash="a" * 64,
    )


def _section_settings(**updates):
    values = {
        "id": "chunk",
        "type": "chunk",
        "algorithm": "section_token",
        "target_tokens": 64,
        "maximum_tokens": 96,
        "overlap_tokens": 16,
    }
    values.update(updates)
    return SectionTokenChunkNodeV2.model_validate(values)


def test_section_chunking_has_hard_bounds_exact_spans_and_embedding_only_heading():
    document = _cleaned(
        [
            CanonicalInputSegment(text="Guide", block_type="heading"),
            CanonicalInputSegment(
                text="First sentence has useful details. Second sentence adds context.",
                block_type="paragraph",
                heading_path=("Guide",),
            ),
            CanonicalInputSegment(
                text="Third sentence is retained faithfully for evidence.",
                block_type="paragraph",
                heading_path=("Guide",),
            ),
        ]
    )
    result = chunk_cleaned_document(document, _section_settings())
    tokenizer = tokenizer_for("utf8-byte-v1")

    assert result.chunks
    assert all(tokenizer.count(chunk.text) <= 96 for chunk in result.chunks)
    assert all(chunk.embedding_text.endswith(chunk.text) for chunk in result.chunks)
    assert all("Section: Guide" not in chunk.text for chunk in result.chunks)
    assert any("Section: Guide" in chunk.embedding_text for chunk in result.chunks)
    for chunk in result.chunks:
        assert chunk.token_count == tokenizer.count(chunk.text)
        assert chunk.embedding_token_count == tokenizer.count(chunk.embedding_text)
        for span in result.spans[chunk.ordinal]:
            block = document.blocks[span.block_ordinal]
            assert (
                chunk.text[span.chunk_start_char : span.chunk_end_char]
                == block.text[span.block_start_char : span.block_end_char]
            )


def test_multilingual_long_word_and_protected_blocks_split_only_at_hard_limit():
    document = _cleaned(
        [
            CanonicalInputSegment(
                text="नमस्ते" * 40,
                block_type="paragraph",
                heading_path=("बहुभाषी",),
            ),
            CanonicalInputSegment(
                text="print('protected')\n" * 5,
                block_type="code",
                heading_path=("बहुभाषी",),
            ),
        ]
    )
    result = chunk_cleaned_document(
        document,
        _section_settings(maximum_tokens=64, overlap_tokens=0),
    )

    assert all(len(chunk.text.encode("utf-8")) <= 64 for chunk in result.chunks)
    assert all(
        chunk.text.encode("utf-8").decode("utf-8") == chunk.text
        for chunk in result.chunks
    )
    assert any(
        finding["code"] == "oversize_block_split"
        for chunk in result.chunks
        for finding in chunk.findings
    )
    assert any(
        finding["code"] == "oversize_protected_block_split"
        for chunk in result.chunks
        for finding in chunk.findings
    )


def test_large_table_repeats_header_and_preserves_row_boundaries():
    table = "| Name | Value |\n| --- | --- |\n" + "".join(
        f"| row-{index} | value-{index} |\n" for index in range(8)
    )
    document = _cleaned(
        [
            CanonicalInputSegment(
                text=table,
                block_type="table",
                heading_path=("Metrics",),
            )
        ]
    )
    result = chunk_cleaned_document(
        document,
        _section_settings(maximum_tokens=96, overlap_tokens=0),
    )

    assert len(result.chunks) > 1
    assert all(
        chunk.text.startswith("| Name | Value |\n| --- | --- |\n")
        for chunk in result.chunks
    )
    assert not any(
        finding["code"] == "oversize_table_row_split"
        for chunk in result.chunks
        for finding in chunk.findings
    )


def test_parent_child_chunks_link_matches_to_saved_parent_evidence():
    document = _cleaned(
        [
            CanonicalInputSegment(text="Operations", block_type="heading"),
            *[
                CanonicalInputSegment(
                    text=(
                        f"Paragraph {index} contains reliable operational context. " * 2
                    ),
                    block_type="paragraph",
                    heading_path=("Operations",),
                )
                for index in range(5)
            ],
        ]
    )
    settings = ParentChildChunkNodeV2(
        id="chunk",
        type="chunk",
        algorithm="parent_child",
        child_target_tokens=64,
        child_maximum_tokens=96,
        child_overlap_tokens=16,
        parent_target_tokens=180,
        parent_maximum_tokens=240,
    )
    first = chunk_cleaned_document(document, settings)
    second = chunk_cleaned_document(document, settings)
    parents = {
        chunk.ordinal: chunk for chunk in first.chunks if chunk.chunk_role == "parent"
    }
    children = [chunk for chunk in first.chunks if chunk.chunk_role == "child"]

    assert first == second
    assert parents and children
    assert all(child.parent_ordinal in parents for child in children)
    assert all(child.text in parents[child.parent_ordinal].text for child in children)
    assert all(child.embedding_text.endswith(child.text) for child in children)


@pytest.mark.parametrize(
    "updates",
    [
        {"target_tokens": 97, "maximum_tokens": 96},
        {"target_tokens": 64, "overlap_tokens": 64},
        {"target_tokens": 63},
    ],
)
def test_section_chunk_bounds_are_server_validated(updates):
    with pytest.raises(ValidationError):
        _section_settings(**updates)
