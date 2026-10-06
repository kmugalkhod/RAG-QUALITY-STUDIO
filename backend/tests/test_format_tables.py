"""formats-v2 tables for DOCX, CSV/TSV and XLSX (Slice 5 of the Extract plan)."""

from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.ingestion_content.extractors import extract_document, pdf as extraction
from app.ingestion_content.extractors.formats import CSV, DOCX, TSV, XLSX
from app.ingestion_content.tables import table_row_groups
from app.schemas.ingestion import ExtractNodeV2


def _package(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _settings(version: str = "layout-ocr-v2", tables: str = "preserve"):
    return ExtractNodeV2(
        id="extract",
        type="extract",
        strategy="auto",
        tables=tables,
        config_version=version,
    )


def _extract(tmp_path, name, content, media_type, **settings):
    path = tmp_path / name
    path.write_bytes(content)
    return extract_document(path, media_type, name, _settings(**settings))


def _cell(value: str) -> str:
    return f"<w:tc><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:tc>"


def _docx(rows: list[list[str]], nested: bool = False) -> bytes:
    table_rows = []
    for index, row in enumerate(rows):
        cells = [_cell(value) for value in row]
        if nested and index == 1:
            cells[-1] = (
                "<w:tc><w:tbl><w:tr>" + _cell("Inner") + "</w:tr></w:tbl></w:tc>"
            )
        table_rows.append("<w:tr>" + "".join(cells) + "</w:tr>")
    return _package(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": (
                '<w:document xmlns:w="urn:w"><w:body>'
                '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                "<w:r><w:t>Register</w:t></w:r></w:p>"
                f"<w:tbl>{''.join(table_rows)}</w:tbl>"
                "</w:body></w:document>"
            ),
        }
    )


def test_docx_table_is_one_header_table_and_follows_the_table_setting(tmp_path):
    rows = [["Name", "Owner"], ["Item 1", "Team 1"], ["Item 2", "Team 2"]]
    document, version = _extract(tmp_path, "r.docx", _docx(rows), DOCX)

    assert version == "formats-v2"
    tables = [block for block in document.blocks if block.type == "table"]
    assert len(tables) == 1
    assert tables[0].text.splitlines()[:2] == ["| Name | Owner |", "| --- | --- |"]
    assert tables[0].attributes["table"]["rows"] == rows
    assert tables[0].heading_path == ["Register"]
    assert document.measurements.table_count == 1

    plain, _ = _extract(tmp_path, "p.docx", _docx(rows), DOCX, tables="plain_text")
    table = next(block for block in plain.blocks if block.type == "table")
    assert table.text.splitlines() == [
        "Name\tOwner",
        "Item 1\tTeam 1",
        "Item 2\tTeam 2",
    ]


def test_docx_nested_table_text_stays_in_its_parent_cell(tmp_path):
    rows = [["Name", "Owner"], ["Item 1", "ignored"]]
    document, _ = _extract(tmp_path, "n.docx", _docx(rows, nested=True), DOCX)
    table = next(block for block in document.blocks if block.type == "table")
    assert table.attributes["table"]["rows"] == [["Name", "Owner"], ["Item 1", "Inner"]]


def test_large_csv_repeats_its_header_in_every_group(tmp_path):
    lines = ["name,team,status"] + [
        f"item-{row}-{'x' * 40},team-{row},open" for row in range(1, 1_201)
    ]
    document, version = _extract(tmp_path, "big.csv", "\n".join(lines).encode(), CSV)

    assert version == "formats-v2"
    tables = [block for block in document.blocks if block.type == "table"]
    assert len(tables) > 1
    assert all(block.text.startswith("| name | team | status |") for block in tables)
    retained = [
        row for block in tables for row in block.attributes["table"]["rows"][1:]
    ]
    assert len(retained) == 1_200
    assert tables[0].attributes["table"]["name"] == "big.csv"
    assert document.measurements.table_count == 1


def test_tsv_and_long_csv_cells_are_kept_whole(tmp_path):
    tsv, _ = _extract(tmp_path, "t.tsv", b"name\tvalue\n alpha \t1\n", TSV)
    assert tsv.blocks[0].attributes["table"]["rows"] == [
        ["name", "value"],
        ["alpha", "1"],
    ]

    long_cell = "word " * 4_000
    csv_text = f'name,notes\nalpha,"{long_cell}"\nbeta,short\n'.encode()
    document, _ = _extract(tmp_path, "long.csv", csv_text, CSV)
    blocks = document.blocks
    assert any(long_cell.strip() in block.text for block in blocks)
    omitted = next(
        block for block in blocks if block.attributes["table"].get("rows_omitted")
    )
    assert omitted.text.startswith("| name | notes |")
    assert omitted.attributes["table"]["truncated"] is False
    assert all(
        len(json.dumps(block.attributes, ensure_ascii=True).encode()) <= 15_500
        for block in blocks
    )


def test_xlsx_keeps_one_table_per_sheet(tmp_path):
    workbook = _package(
        {
            "[Content_Types].xml": "<Types/>",
            "xl/workbook.xml": "<workbook/>",
            "xl/sharedStrings.xml": (
                "<sst xmlns='urn:x'><si><t>Head</t></si><si><t>Value</t></si></sst>"
            ),
            "xl/worksheets/sheet1.xml": (
                "<worksheet xmlns='urn:x'><sheetData>"
                "<row><c t='s'><v>0</v></c><c t='inlineStr'><is><t>Total</t></is></c></row>"
                "<row><c t='s'><v>1</v></c><c><f>SUM(A1)</f><v>3</v></c></row>"
                "</sheetData></worksheet>"
            ),
            "xl/worksheets/sheet2.xml": (
                "<worksheet xmlns='urn:x'><sheetData>"
                "<row><c t='inlineStr'><is><t>Other</t></is></c></row>"
                "</sheetData></worksheet>"
            ),
        }
    )
    document, _ = _extract(tmp_path, "book.xlsx", workbook, XLSX)
    tables = [block for block in document.blocks if block.type == "table"]

    assert [block.page_number for block in tables] == [1, 2]
    assert tables[0].attributes["table"]["rows"] == [
        ["Head", "Total"],
        ["Value", "=SUM(A1)"],
    ]
    assert tables[0].attributes["table"]["sheet"] == 1
    assert document.measurements.table_count == 2


def test_v1_keeps_one_block_per_row(tmp_path):
    rows = [["Name", "Owner"], ["Item 1", "Team 1"]]
    document, version = _extract(
        tmp_path, "v1.docx", _docx(rows), DOCX, version="layout-ocr-v1"
    )
    assert version == "formats-v1"
    assert [block.text for block in document.blocks if block.type == "table"] == [
        "| Name | Owner |",
        "| Item 1 | Team 1 |",
    ]


def test_a_header_wider_than_the_budget_omits_structured_copies():
    header = [f"column-{index}-" + "h" * 20 for index in range(1_000)]
    groups, limited = table_row_groups(
        [header, ["v"] * 1_000],
        "markdown",
        table_id="t1",
        max_rows=10,
        max_columns=1_000,
        max_cell_characters=None,
    )
    assert limited is False
    evidence, attributes, _, _ = groups[0]
    assert attributes["table"]["header_omitted"] is True
    assert len(json.dumps(attributes, ensure_ascii=True).encode()) <= 15_500
    assert header[-1] in evidence


def test_v2_processing_identity_names_formats_v2():
    assert "formats-v2" in extraction.extractor_version_for_settings(_settings())
    assert "formats-v1" in extraction.extractor_version_for_settings(
        _settings("layout-ocr-v1")
    )
