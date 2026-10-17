"""Spec 0012 Part D: section-token-v3 and parent-child-v3."""

from copy import deepcopy

import pytest

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    chunk_cleaned_document,
    chunker_version_for_node,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.chunking import HEADING_PREFIX_BYTES, SHORT_CHUNK_TOKENS
from app.ingestion_content.cleaning import default_structure_steps
from app.ingestion_content.tokenizers import tokenizer_for
from app.schemas.ingestion import (
    CleanNodeV2,
    ParentChildChunkNodeV2,
    SectionTokenChunkNodeV2,
)

TOKENIZER = tokenizer_for("utf8-byte-v1")
WORDS = " ".join(
    f"{word}{index}"
    for index, word in enumerate(
        ["harbour", "terminal", "passengers", "ferry", "schedule", "platform"] * 30
    )
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


def _paragraphs(*texts, heading=None, page=1):
    segments = []
    path = ()
    if heading:
        segments.append(
            CanonicalInputSegment(text=heading, block_type="heading", page_number=page)
        )
        path = (heading,)
    segments.extend(
        CanonicalInputSegment(
            text=text, block_type="paragraph", heading_path=path, page_number=page
        )
        for text in texts
    )
    return _cleaned(segments)


def _section(version, **updates):
    values = {
        "id": "chunk",
        "type": "chunk",
        "algorithm": "section_token",
        "config_version": version,
    }
    values.update(updates)
    return SectionTokenChunkNodeV2.model_validate(values)


def _parent_child(version, **updates):
    values = {
        "id": "chunk",
        "type": "chunk",
        "algorithm": "parent_child",
        "config_version": version,
    }
    values.update(updates)
    return ParentChildChunkNodeV2.model_validate(values)


def _exact_spans(document, result):
    for chunk in result.chunks:
        for span in result.spans[chunk.ordinal]:
            block = document.blocks[span.block_ordinal]
            assert (
                chunk.text[span.chunk_start_char : span.chunk_end_char]
                == block.text[span.block_start_char : span.block_end_char]
            )


def _mid_word_starts(document, result):
    count = 0
    for chunk in result.chunks:
        span = result.spans[chunk.ordinal][0]
        text = document.blocks[span.block_ordinal].text
        start = span.block_start_char
        if (
            0 < start < len(text)
            and text[start - 1].isalnum()
            and text[start].isalnum()
        ):
            count += 1
    return count


def _mid_word_ends(document, result):
    count = 0
    for chunk in result.chunks:
        span = result.spans[chunk.ordinal][-1]
        text = document.blocks[span.block_ordinal].text
        end = span.block_end_char
        if 0 < end < len(text) and text[end - 1].isalnum() and text[end].isalnum():
            count += 1
    return count


def test_hard_splits_fall_back_to_whitespace():
    document = _paragraphs(WORDS)
    sizes = {"target_tokens": 64, "maximum_tokens": 100, "overlap_tokens": 0}

    v2 = chunk_cleaned_document(document, _section("section-token-v2", **sizes))
    v3 = chunk_cleaned_document(document, _section("section-token-v3", **sizes))

    assert _mid_word_starts(document, v2) > 0
    assert _mid_word_starts(document, v3) == 0
    assert _mid_word_ends(document, v3) == 0
    assert all(chunk.token_count <= 100 for chunk in v3.chunks)
    # Without overlap the passages hold the paragraph exactly once.
    assert "".join(chunk.text for chunk in v3.chunks) == WORDS
    _exact_spans(document, v3)


def test_full_width_sentence_ends_are_boundaries():
    sentence = "港湾ターミナルは毎朝六時に開きます。"
    text = sentence * 8
    document = _paragraphs(text)
    sizes = {"target_tokens": 64, "maximum_tokens": 120, "overlap_tokens": 0}

    v2 = chunk_cleaned_document(document, _section("section-token-v2", **sizes))
    v3 = chunk_cleaned_document(document, _section("section-token-v3", **sizes))

    assert any(not chunk.text.endswith("。") for chunk in v2.chunks[:-1])
    assert all(chunk.text.endswith("。") for chunk in v3.chunks)
    assert all(chunk.text.startswith("港") for chunk in v3.chunks)
    _exact_spans(document, v3)


def test_overlap_starts_at_a_word():
    first = WORDS[:380].rsplit(" ", 1)[0] + "."
    second = "The ferry leaves the harbour terminal at nine every weekday morning."
    document = _paragraphs(first, second, first, second)
    sizes = {"target_tokens": 300, "maximum_tokens": 500, "overlap_tokens": 37}

    v2 = chunk_cleaned_document(document, _section("section-token-v2", **sizes))
    v3 = chunk_cleaned_document(document, _section("section-token-v3", **sizes))

    assert _mid_word_starts(document, v2) > 0
    assert _mid_word_starts(document, v3) == 0
    _exact_spans(document, v3)


def test_a_short_remainder_joins_its_neighbour():
    # Two sentences fill one passage; the last few words would stand alone.
    long_sentence = "The harbour terminal opens at six. " * 5
    text = long_sentence + "Bring a ticket."
    document = _paragraphs(text)
    sizes = {"target_tokens": 64, "maximum_tokens": 180, "overlap_tokens": 0}

    v2 = chunk_cleaned_document(document, _section("section-token-v2", **sizes))
    v3 = chunk_cleaned_document(document, _section("section-token-v3", **sizes))

    assert min(chunk.token_count for chunk in v2.chunks) < SHORT_CHUNK_TOKENS
    assert min(chunk.token_count for chunk in v3.chunks) >= SHORT_CHUNK_TOKENS
    assert all(chunk.token_count <= 180 for chunk in v3.chunks)
    _exact_spans(document, v3)


def test_a_group_adding_under_40_bytes_after_its_overlap_joins_the_one_before():
    paragraphs = [
        f"Paragraph {index} about the terminal and ferries." for index in range(4)
    ]
    paragraphs.append("Last note.")
    document = _paragraphs(*paragraphs)
    sizes = {"target_tokens": 150, "maximum_tokens": 400, "overlap_tokens": 60}

    v2 = chunk_cleaned_document(document, _section("section-token-v2", **sizes))
    v3 = chunk_cleaned_document(document, _section("section-token-v3", **sizes))

    assert v2.chunks[-1].text.endswith("Last note.")
    assert len(v3.chunks) == len(v2.chunks) - 1
    assert v3.chunks[-1].text.endswith("Last note.")
    _exact_spans(document, v3)


def test_a_short_first_section_joins_the_next_one_on_its_page():
    document = _cleaned(
        [
            CanonicalInputSegment(text="Draft", block_type="paragraph", page_number=1),
            CanonicalInputSegment(
                text="Timetable", block_type="heading", page_number=1
            ),
            CanonicalInputSegment(
                text="Ferries leave the harbour terminal every hour from six.",
                block_type="paragraph",
                heading_path=("Timetable",),
                page_number=1,
            ),
        ]
    )

    v2 = chunk_cleaned_document(document, _section("section-token-v2"))
    v3 = chunk_cleaned_document(document, _section("section-token-v3"))

    assert [chunk.text for chunk in v2.chunks][0] == "Draft"
    assert len(v3.chunks) == 1
    assert v3.chunks[0].text.startswith("Draft\n\nTimetable")
    assert v3.chunks[0].provenance["section_path"] == ["Timetable"]
    _exact_spans(document, v3)


def test_prefix_leaves_out_the_heading_the_passage_starts_with():
    document = _cleaned(
        [
            CanonicalInputSegment(text="Guide", block_type="heading", page_number=1),
            CanonicalInputSegment(
                text="This guide covers the harbour terminal and its ferries.",
                block_type="paragraph",
                heading_path=("Guide",),
                page_number=1,
            ),
            CanonicalInputSegment(
                text="Timetable",
                block_type="heading",
                heading_path=("Guide",),
                page_number=1,
            ),
            CanonicalInputSegment(
                text="Ferries leave the harbour terminal every hour from six.",
                block_type="paragraph",
                heading_path=("Guide", "Timetable"),
                page_number=1,
            ),
        ]
    )

    v2 = chunk_cleaned_document(document, _section("section-token-v2"))
    v3 = chunk_cleaned_document(document, _section("section-token-v3"))

    timetable = next(c for c in v2.chunks if c.text.startswith("Timetable"))
    assert timetable.embedding_text.startswith(
        "Section: Guide > Timetable\n\nTimetable"
    )
    timetable = next(c for c in v3.chunks if c.text.startswith("Timetable"))
    assert timetable.embedding_text == f"Section: Guide\n\n{timetable.text}"
    # Citations keep the full heading path.
    assert timetable.provenance["section_path"] == ["Guide", "Timetable"]
    guide = v3.chunks[0]
    assert guide.text.startswith("Guide\n\n")
    assert guide.provenance["embedding_prefix"] == ""


def test_prefix_is_always_capped():
    heading = "Harbour terminal regulations " * 15
    document = _paragraphs(
        "Ferries leave the harbour terminal every hour from six.", heading=heading
    )
    document = _cleaned(
        [
            CanonicalInputSegment(text=heading, block_type="heading", page_number=1),
            CanonicalInputSegment(
                text="Ferries leave the harbour terminal every hour from six.",
                block_type="paragraph",
                heading_path=(heading, "Timetable"),
                page_number=1,
            ),
        ]
    )

    v2 = chunk_cleaned_document(document, _section("section-token-v2"))
    v3 = chunk_cleaned_document(document, _section("section-token-v3"))

    assert (
        TOKENIZER.count(v2.chunks[-1].provenance["embedding_prefix"])
        > HEADING_PREFIX_BYTES
    )
    for chunk in v3.chunks:
        assert (
            TOKENIZER.count(chunk.provenance["embedding_prefix"])
            <= HEADING_PREFIX_BYTES
        )


def test_parent_child_v3_children_and_parents_start_at_words():
    document = _paragraphs(WORDS, WORDS[:600], heading="Timetable")
    v2 = chunk_cleaned_document(document, _parent_child("parent-child-v2"))
    v3 = chunk_cleaned_document(document, _parent_child("parent-child-v3"))

    assert _mid_word_starts(document, v2) > 0
    assert _mid_word_starts(document, v3) == 0
    children = [chunk for chunk in v3.chunks if chunk.chunk_role == "child"]
    assert children and all(c.token_count >= SHORT_CHUNK_TOKENS for c in children)
    assert all(
        child.parent_ordinal is not None
        and v3.chunks[child.parent_ordinal].chunk_role == "parent"
        for child in children
    )
    _exact_spans(document, v3)


@pytest.mark.parametrize(
    ("node", "label"),
    [
        (_section("section-token-v1"), "section-token-v2"),
        (_section("section-token-v2"), "section-token-v2"),
        (_section("section-token-v3"), "section-token-v3"),
        (_parent_child("parent-child-v1"), "parent-child-v2"),
        (_parent_child("parent-child-v3"), "parent-child-v3"),
    ],
)
def test_chunker_label(node, label):
    # v1 and v2 keep the label every saved index already records.
    assert chunker_version_for_node(node) == label
