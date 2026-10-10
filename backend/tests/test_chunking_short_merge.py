"""Spec 0010: section-token-v2 and parent-child-v2 merge short section starts."""

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

BODY = (
    "Les maladies du système circulatoire restent la première cause de décès "
    "dans l'Union européenne, devant les cancers et les maladies respiratoires."
)
CALLOUT = "381 décès"
LABEL = "pour 100 000"


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


def _section(version="section-token-v2", **updates):
    values = {
        "id": "chunk",
        "type": "chunk",
        "algorithm": "section_token",
        "config_version": version,
    }
    values.update(updates)
    return SectionTokenChunkNodeV2.model_validate(values)


def _parent_child(version="parent-child-v2", **updates):
    values = {
        "id": "chunk",
        "type": "chunk",
        "algorithm": "parent_child",
        "config_version": version,
    }
    values.update(updates)
    return ParentChildChunkNodeV2.model_validate(values)


def _chart_page(callout_page=21, label_page=21):
    """A body section, then a callout and a label each read as a bodiless heading."""

    return _cleaned(
        [
            CanonicalInputSegment(
                text="Causes de décès", block_type="heading", page_number=21
            ),
            CanonicalInputSegment(
                text=BODY,
                block_type="paragraph",
                heading_path=("Causes de décès",),
                page_number=21,
            ),
            CanonicalInputSegment(
                text=CALLOUT,
                block_type="heading",
                heading_path=("Causes de décès",),
                page_number=callout_page,
            ),
            CanonicalInputSegment(
                text=LABEL,
                block_type="heading",
                heading_path=("Causes de décès",),
                page_number=label_page,
            ),
        ]
    )


def _assert_exact_spans(document, result):
    for chunk in result.chunks:
        for span in result.spans[chunk.ordinal]:
            block = document.blocks[span.block_ordinal]
            assert (
                chunk.text[span.chunk_start_char : span.chunk_end_char]
                == block.text[span.block_start_char : span.block_end_char]
            )


def test_v1_keeps_short_heading_chunks_on_their_own():
    result = chunk_cleaned_document(_chart_page(), _section("section-token-v1"))

    assert [chunk.text for chunk in result.chunks] == [
        f"Causes de décès\n\n{BODY}",
        CALLOUT,
        LABEL,
    ]


def test_v2_appends_a_run_of_short_chunks_to_the_chunk_before_on_the_page():
    document = _chart_page()
    result = chunk_cleaned_document(document, _section())

    assert [chunk.text for chunk in result.chunks] == [
        f"Causes de décès\n\n{BODY}\n\n{CALLOUT}\n\n{LABEL}"
    ]
    chunk = result.chunks[0]
    assert chunk.page_number == 21
    assert chunk.provenance["section_path"] == ["Causes de décès"]
    assert chunk.embedding_text == f"Section: Causes de décès\n\n{chunk.text}"
    assert chunk.token_count == tokenizer_for("utf8-byte-v1").count(chunk.text)
    _assert_exact_spans(document, result)


def test_v2_never_merges_across_pages():
    result = chunk_cleaned_document(
        _chart_page(callout_page=22, label_page=22), _section()
    )

    assert [chunk.text for chunk in result.chunks] == [
        f"Causes de décès\n\n{BODY}",
        f"{CALLOUT}\n\n{LABEL}",
    ]
    assert [chunk.page_number for chunk in result.chunks] == [21, 22]


def test_v2_merges_pageless_documents():
    document = _cleaned(
        [
            CanonicalInputSegment(text="Word limit", block_type="heading"),
            CanonicalInputSegment(
                text=BODY, block_type="paragraph", heading_path=("Word limit",)
            ),
            CanonicalInputSegment(
                text="500 words", block_type="heading", heading_path=("Word limit",)
            ),
        ]
    )
    result = chunk_cleaned_document(document, _section())

    assert [chunk.text for chunk in result.chunks] == [
        f"Word limit\n\n{BODY}\n\n500 words"
    ]
    assert result.chunks[0].page_number is None


def test_v2_keeps_a_chunk_of_40_tokens_or_more_on_its_own():
    long_label = "x" * 40
    document = _cleaned(
        [
            CanonicalInputSegment(
                text=BODY, block_type="paragraph", heading_path=("A",), page_number=1
            ),
            CanonicalInputSegment(
                text=long_label,
                block_type="heading",
                heading_path=("A",),
                page_number=1,
            ),
        ]
    )
    result = chunk_cleaned_document(document, _section())

    assert [chunk.text for chunk in result.chunks] == [BODY, long_label]


def test_v2_does_not_merge_past_the_hard_maximum():
    filler = "Mot " * 24  # 96 tokens, the hard maximum
    document = _cleaned(
        [
            CanonicalInputSegment(
                text=filler.strip(),
                block_type="paragraph",
                heading_path=("A",),
                page_number=1,
            ),
            CanonicalInputSegment(
                text=CALLOUT, block_type="heading", heading_path=("A",), page_number=1
            ),
        ]
    )
    settings = _section(target_tokens=64, maximum_tokens=96, overlap_tokens=16)
    result = chunk_cleaned_document(document, settings)

    assert result.chunks[-1].text == CALLOUT
    assert all(chunk.token_count <= 96 for chunk in result.chunks)


def test_v2_merges_only_a_section_start_into_the_last_chunk_of_the_section_before():
    sentences = " ".join(f"Sentence {index} carries detail." for index in range(12))
    document = _cleaned(
        [
            CanonicalInputSegment(
                text=sentences,
                block_type="paragraph",
                heading_path=("A",),
                page_number=1,
            ),
            CanonicalInputSegment(
                text=CALLOUT, block_type="heading", heading_path=("A",), page_number=1
            ),
        ]
    )
    settings = _section(target_tokens=64, maximum_tokens=200, overlap_tokens=16)
    v1 = chunk_cleaned_document(
        document,
        _section(
            "section-token-v1", target_tokens=64, maximum_tokens=200, overlap_tokens=16
        ),
    )
    v2 = chunk_cleaned_document(document, settings)

    assert [chunk.text for chunk in v2.chunks[:-1]] == [
        chunk.text for chunk in v1.chunks[:-2]
    ]
    assert v2.chunks[-1].text == f"{v1.chunks[-2].text}\n\n{CALLOUT}"
    assert len(v2.chunks) == len(v1.chunks) - 1
    _assert_exact_spans(document, v2)


def test_parent_child_v2_merges_into_the_parent_and_the_child_before():
    document = _chart_page()
    v1 = chunk_cleaned_document(document, _parent_child("parent-child-v1"))
    v2 = chunk_cleaned_document(document, _parent_child())

    assert [chunk.text for chunk in v1.chunks if chunk.chunk_role == "child"] == [
        f"Causes de décès\n\n{BODY}",
        CALLOUT,
        LABEL,
    ]
    parents = [chunk for chunk in v2.chunks if chunk.chunk_role == "parent"]
    children = [chunk for chunk in v2.chunks if chunk.chunk_role == "child"]
    merged = f"Causes de décès\n\n{BODY}\n\n{CALLOUT}\n\n{LABEL}"
    assert [chunk.text for chunk in parents] == [merged]
    assert [chunk.text for chunk in children] == [merged]
    assert children[0].parent_ordinal == parents[0].ordinal
    _assert_exact_spans(document, v2)


def test_parent_child_v2_children_stay_inside_their_parent():
    paragraphs = [
        CanonicalInputSegment(
            text=f"Paragraph {index} contains reliable operational context. " * 2,
            block_type="paragraph",
            heading_path=("Operations",),
            page_number=3,
        )
        for index in range(5)
    ]
    labels = [
        CanonicalInputSegment(
            text=f"Label {index}",
            block_type="heading",
            heading_path=("Operations",),
            page_number=3,
        )
        for index in range(3)
    ]
    document = _cleaned([*paragraphs, labels[0], paragraphs[0], *labels[1:]])
    result = chunk_cleaned_document(
        document,
        _parent_child(
            child_target_tokens=64,
            child_maximum_tokens=160,
            child_overlap_tokens=16,
            parent_target_tokens=180,
            parent_maximum_tokens=400,
        ),
    )
    parents = {
        chunk.ordinal: chunk for chunk in result.chunks if chunk.chunk_role == "parent"
    }
    children = [chunk for chunk in result.chunks if chunk.chunk_role == "child"]

    assert all(child.text in parents[child.parent_ordinal].text for child in children)
    assert not [chunk for chunk in result.chunks if chunk.token_count < 40]
    _assert_exact_spans(document, result)


@pytest.mark.parametrize(
    ("factory", "version"),
    [(_section, "section-token-v3"), (_parent_child, "parent-child-v3")],
)
def test_unknown_chunking_versions_are_rejected(factory, version):
    with pytest.raises(ValidationError):
        factory(version)


def test_saved_configuration_without_a_version_stays_v1():
    assert (
        SectionTokenChunkNodeV2.model_validate(
            {"id": "chunk", "type": "chunk", "algorithm": "section_token"}
        ).config_version
        == "section-token-v1"
    )
    assert (
        ParentChildChunkNodeV2.model_validate(
            {"id": "chunk", "type": "chunk", "algorithm": "parent_child"}
        ).config_version
        == "parent-child-v1"
    )
