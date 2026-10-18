"""Spec 0014 Part B: section-token-v4 and parent-child-v4 table row passages."""

from copy import deepcopy
from dataclasses import replace

import pytest

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    chunk_cleaned_document,
    chunker_version_for_node,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import default_structure_steps
from app.ingestion_content.tables import table_row_groups
from app.schemas.ingestion import (
    CleanNodeV2,
    ParentChildChunkNodeV2,
    SectionTokenChunkNodeV2,
)

CAPTION = "Table A-2. Households by Total Money Income"
HEADER = ["Race and year", "Number (thousands)", "Median income Estimate"]


def _table(rows, *, page=1, caption=CAPTION, mode="preserve", table_id="p1-t1"):
    groups, _ = table_row_groups(
        [HEADER, *rows],
        mode,
        table_id=table_id,
        max_rows=2000,
        max_columns=50,
        max_cell_characters=None,
        base_attributes={"origin": "layout", "engine": "pymupdf"},
    )
    segments = []
    for evidence, attributes, _, _ in groups:
        attributes["table"]["caption"] = caption
        segments.append(
            CanonicalInputSegment(
                text=evidence,
                block_type="table",
                page_number=page,
                heading_path=("APPENDIX A", caption),
                attributes=attributes,
            )
        )
    return segments


def _cleaned(segments):
    extracted = build_extracted_document(segments, media_type="application/pdf")
    clean = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v2",
        steps=deepcopy(default_structure_steps()),
    )
    return clean_document(
        extracted,
        clean,
        cleaner_for_node(clean),
        extractor_version="test-extractor-v1",
        configuration_hash="a" * 64,
    )


def _section(version="section-token-v4", **updates):
    return SectionTokenChunkNodeV2.model_validate(
        {
            "id": "chunk",
            "type": "chunk",
            "algorithm": "section_token",
            "config_version": version,
            **updates,
        }
    )


def _parent_child(version="parent-child-v4", **updates):
    return ParentChildChunkNodeV2.model_validate(
        {
            "id": "chunk",
            "type": "chunk",
            "algorithm": "parent_child",
            "config_version": version,
            **updates,
        }
    )


ROWS = [
    ["ALL RACES", "", ""],
    ["2015", "125,800", "68,410"],
    ["1990", "93,350", "76,820"],
    ["WHITE ALONE", "", ""],
    ["2015", "98,300", "73,180"],
]


def _chunks(segments, settings):
    return chunk_cleaned_document(_cleaned(segments), settings).chunks


def test_each_row_is_a_passage_with_header_label_and_column_values():
    chunks = _chunks(
        [
            CanonicalInputSegment(
                text="Table A-2.\nHouseholds by Total Money Income",
                block_type="paragraph",
                page_number=1,
                heading_path=("APPENDIX A", CAPTION),
            ),
            *_table(ROWS),
        ],
        _section(),
    )
    rows = [c for c in chunks if c.provenance.get("table_passage") == "row-v1"]
    assert len(rows) == 3
    first = rows[0]
    assert first.text.splitlines() == [
        "| Race and year | Number (thousands) | Median income Estimate |",
        "| --- | --- | --- |",
        "| ALL RACES |  |  |",
        "| 2015 | 125,800 | 68,410 |",
    ]
    assert first.embedding_text == (
        "Section: APPENDIX A > Table A-2. Households by Total Money Income\n\n"
        "ALL RACES. Race and year: 2015; Number (thousands): 125,800; "
        "Median income Estimate: 68,410"
    )
    assert rows[1].embedding_text.endswith(
        "ALL RACES. Race and year: 1990; Number (thousands): 93,350; "
        "Median income Estimate: 76,820"
    )
    assert "| ALL RACES |" in rows[1].text
    assert rows[2].embedding_text.endswith(
        "WHITE ALONE. Race and year: 2015; "
        "Number (thousands): 98,300; "
        "Median income Estimate: 73,180"
    )
    assert "ALL RACES" not in rows[2].text
    # The caption paragraph stays a passage of its own, not merged into a row.
    assert chunks[0].text.startswith("Table A-2.")
    assert chunks[0].provenance.get("table_passage") is None


def test_row_passage_spans_point_at_the_exact_source_lines():
    cleaned = _cleaned(_table(ROWS))
    result = chunk_cleaned_document(cleaned, _section())
    block = cleaned.blocks[0]
    for chunk in result.chunks:
        pieces = [
            block.text[span.block_start_char : span.block_end_char]
            for span in result.spans[chunk.ordinal]
        ]
        assert "".join(pieces) == chunk.text


def test_wrapped_group_labels_join_and_carry_to_the_next_page():
    segments = [
        *_table(
            [
                ["AMERICAN INDIAN", "", ""],
                ["AND ALASKA NATIVE", "", ""],
                ["2022", "2,464", "58,060"],
            ]
        ),
        *_table(
            [["2021", "2,475", "55,300"]],
            page=2,
            caption=CAPTION + "—Con.",
            table_id="p2-t1",
        ),
    ]
    rows = [
        c
        for c in _chunks(segments, _section())
        if c.provenance.get("table_passage") == "row-v1"
    ]
    assert (
        "AMERICAN INDIAN AND ALASKA NATIVE. Race and year: 2022"
        in rows[0].embedding_text
    )
    # On the continuation page the label is searched but not shown as text.
    assert (
        "AMERICAN INDIAN AND ALASKA NATIVE. Race and year: 2021"
        in rows[1].embedding_text
    )
    assert "AMERICAN" not in rows[1].text


def test_a_trailing_group_label_gets_its_own_passage():
    rows = [
        c
        for c in _chunks(_table([["2015", "1", "2"], ["NOTES", "", ""]]), _section())
        if c.provenance.get("table_passage") == "row-v1"
    ]
    assert rows[-1].embedding_text.endswith("\n\nNOTES")


def test_plain_text_tables_give_row_passages_too():
    rows = [
        c
        for c in _chunks(_table(ROWS[:2], mode="plain_text"), _section())
        if c.provenance.get("table_passage") == "row-v1"
    ]
    assert rows[0].text.splitlines() == [
        "Race and year\tNumber (thousands)\tMedian income Estimate",
        "ALL RACES\t\t",
        "2015\t125,800\t68,410",
    ]


def test_tables_whose_text_does_not_match_their_rows_are_chunked_as_in_v3():
    segments = _table(ROWS)
    attributes = deepcopy(segments[0].attributes)
    attributes["table"]["rows"] = attributes["table"]["rows"][:-1]
    segments = [replace(segments[0], attributes=attributes)]
    v4 = _chunks(segments, _section())
    v3 = _chunks(segments, _section("section-token-v3"))
    assert [c.text for c in v4] == [c.text for c in v3]
    assert all(c.provenance.get("table_passage") is None for c in v4)


def test_a_header_too_large_for_the_passage_is_left_to_the_row_alone():
    wide = [f"Column {index} with a long descriptive name" for index in range(3)]
    groups, _ = table_row_groups(
        [wide, ["2015", "1", "2"]],
        "preserve",
        table_id="t",
        max_rows=10,
        max_columns=10,
        max_cell_characters=None,
    )
    evidence, attributes, _, _ = groups[0]
    segment = CanonicalInputSegment(
        text=evidence, block_type="table", page_number=1, attributes=attributes
    )
    chunks = _chunks(
        [segment], _section(target_tokens=64, maximum_tokens=64, overlap_tokens=0)
    )
    assert [c.text for c in chunks] == ["| 2015 | 1 | 2 |"]
    assert "Column 0 with a long descriptive name: 2015" in chunks[0].embedding_text


def test_v3_tables_are_unchanged():
    segments = _table(ROWS)
    chunks = _chunks(segments, _section("section-token-v3"))
    assert len(chunks) == 1
    assert chunks[0].embedding_text.endswith(chunks[0].text)


def test_parent_child_v4_keeps_v3_parents_and_makes_rows_children():
    segments = _table(ROWS)
    v3 = _chunks(segments, _parent_child("parent-child-v3"))
    v4 = _chunks(segments, _parent_child())
    parents = lambda chunks: [c.text for c in chunks if c.chunk_role == "parent"]  # noqa: E731
    assert parents(v4) == parents(v3)
    children = [c for c in v4 if c.chunk_role == "child"]
    assert len(children) == 3
    assert all(c.provenance.get("table_passage") == "row-v1" for c in children)
    assert all(c.parent_ordinal == 0 for c in children)


@pytest.mark.parametrize("version", ["section-token-v4", "parent-child-v4"])
def test_v4_reports_its_own_chunker_version(version):
    settings = _section(version) if version.startswith("section") else _parent_child()
    assert chunker_version_for_node(settings) == version
