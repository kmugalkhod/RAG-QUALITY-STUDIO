"""layout-ocr-v2 PDF tables (Slice 2 of docs/extract-node-improvement-plan.md)."""

from __future__ import annotations

import json
from copy import deepcopy

from app.ingestion_content import (
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import default_structure_steps
from app.ingestion_content.extractors import pdf as extraction
from app.ingestion_content.tokenizers import tokenizer_for
from app.schemas.ingestion import CleanNodeV2, SectionTokenChunkNodeV2
from extract_corpus import (
    expectations,
    extract,
    extract_settings,
    large_table_cells,
    save_large_table_pdf,
)


def _grid(rows: int, columns: int, width: int = 40) -> list[list[str]]:
    header = [f"Heading {column}" for column in range(columns)]
    body = [
        [f"r{row}c{column}-" + "x" * width for column in range(columns)]
        for row in range(1, rows + 1)
    ]
    return [header, *body]


def test_large_table_splits_into_header_repeating_groups_within_budget():
    rows = _grid(300, 8)
    groups, limited = extraction._table_row_groups(rows, "markdown", table_id="p1-t1")

    assert limited is False
    assert len(groups) > 1
    retained = []
    expected_start = 1
    for index, (evidence, attributes, first, last) in enumerate(groups):
        table = attributes["table"]
        assert len(json.dumps(attributes, ensure_ascii=True).encode()) <= 15_500
        assert table["rows"][0] == rows[0]
        assert evidence.startswith("| Heading 0 | Heading 1 |")
        assert (table["row_start"], table["row_end"]) == (first, last)
        assert first == expected_start
        assert table["group_index"] == index
        assert table["group_count"] == len(groups)
        assert table["header_repeated"] is (index > 0)
        assert table["table_id"] == "p1-t1"
        assert table["row_count"] == 301
        assert table["truncated"] is False
        retained.extend(table["rows"][1:])
        expected_start = last + 1
    assert retained == rows[1:]


def test_plain_text_groups_use_tab_separated_rows():
    groups, _ = extraction._table_row_groups(_grid(3, 2), "plain_text", table_id="t")
    evidence, attributes, _, _ = groups[0]
    assert evidence.splitlines()[0] == "Heading 0\tHeading 1"
    assert attributes["evidence_rendering"] == "plain_text"


def test_only_safety_limits_mark_a_table_as_cut():
    over_rows, limited = extraction._table_row_groups(
        _grid(extraction.MAX_TABLE_V2_ROWS, 2, width=1), "markdown", table_id="t"
    )
    assert limited is True
    assert over_rows[-1][1]["table"]["row_end"] == extraction.MAX_TABLE_V2_ROWS - 1
    assert all(group[1]["table"]["truncated"] for group in over_rows)


def test_a_row_wider_than_the_budget_keeps_its_full_evidence():
    rows = [["h"] * 20, ["short"] * 20, ["y" * 1_000] * 20, ["after"] * 20]
    groups, limited = extraction._table_row_groups(rows, "markdown", table_id="t")

    assert limited is False
    assert [(first, last) for _, _, first, last in groups] == [(1, 1), (2, 2), (3, 3)]
    evidence, attributes, _, _ = groups[1]
    assert evidence.count("y" * 1_000) == 20
    assert evidence.startswith("| h | h |")
    assert attributes["table"]["rows_omitted"] is True
    assert "rows" not in attributes["table"]
    assert attributes["table"]["header_row"] == ["h"] * 20
    assert all(
        len(json.dumps(group[1], ensure_ascii=True).encode()) <= 15_500
        for group in groups
    )
    assert "rows" in groups[0][1]["table"] and "rows" in groups[2][1]["table"]


def test_v2_publishes_a_whole_40_row_table_under_balanced(tmp_path):
    path = tmp_path / "large-table.pdf"
    save_large_table_pdf(path)
    document = extract(
        path, "application/pdf", extract_settings("layout_aware", "layout-ocr-v2")
    )

    tables = [block for block in document.blocks if block.type == "table"]
    cells = {
        cell
        for block in tables
        for row in block.attributes["table"]["rows"]
        for cell in row
    }
    assert set(large_table_cells()) <= cells
    assert document.measurements.table_count == 1
    assert document.measurements.malformed_table_count == 0
    assert "malformed_tables" not in {finding.code for finding in document.findings}
    assert document.measurements.quality_decision == "pass"
    assert all(
        block.attributes["table"]["header_row"]
        == expectations()["large_table"]["header"]
        for block in tables
    )


def test_v2_table_rows_reach_chunks_with_their_header(tmp_path):
    path = tmp_path / "large-table.pdf"
    save_large_table_pdf(path)
    extracted = extract(
        path, "application/pdf", extract_settings("layout_aware", "layout-ocr-v2")
    )
    clean = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=deepcopy(default_structure_steps()),
    )
    cleaned = clean_document(
        extracted,
        clean,
        cleaner_for_node(clean),
        extractor_version=extraction.LAYOUT_OCR_V2_EXTRACTOR_VERSION,
        configuration_hash="b" * 64,
    )
    settings = SectionTokenChunkNodeV2.model_validate(
        {
            "id": "chunk",
            "type": "chunk",
            "algorithm": "section_token",
            "target_tokens": 600,
            "maximum_tokens": 800,
            "overlap_tokens": 80,
        }
    )
    chunks = chunk_cleaned_document(cleaned, settings).chunks
    tokenizer = tokenizer_for("utf8-byte-v1")
    table_chunks = [
        chunk for chunk in chunks if "R01C1" in chunk.text or "C1 |" in chunk.text
    ]

    assert len(table_chunks) > 1
    assert all(tokenizer.count(chunk.text) <= 800 for chunk in chunks)
    assert all(chunk.text.startswith("| Col1 | Col2 |") for chunk in table_chunks)
    joined = "\n".join(chunk.text for chunk in chunks)
    assert all(cell in joined for cell in large_table_cells())
