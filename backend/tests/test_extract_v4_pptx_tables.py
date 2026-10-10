"""layout-ocr-v4 (spec 0008, B2): PowerPoint table frames are read as tables."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.ingestion_content.extractors import extract_document
from app.ingestion_content.extractors.formats import PPTX
from app.ingestion_content.processing import IngestionStageError
from extract_corpus import extract_settings

NS = "xmlns:p='urn:p' xmlns:a='urn:a'"


def _shape(text: str) -> str:
    return f"<p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>"


def _cell(text: str, **attributes: str) -> str:
    extra = "".join(f" {key}='{value}'" for key, value in attributes.items())
    paragraphs = "".join(
        f"<a:p><a:r><a:t>{part}</a:t></a:r></a:p>" for part in text.split("|") if part
    )
    return f"<a:tc{extra}><a:txBody>{paragraphs or '<a:p/>'}</a:txBody></a:tc>"


def _table(rows: list[str]) -> str:
    return (
        "<p:graphicFrame><a:graphic><a:graphicData><a:tbl>"
        + "".join(f"<a:tr>{row}</a:tr>" for row in rows)
        + "</a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
    )


RATINGS = _table(
    [
        _cell("Probability")
        + _cell("Rating")
        + _cell("Severity of impact")
        + _cell("Rating"),
        _cell("Almost certain") + _cell("5") + _cell("Catastrophic") + _cell("5"),
        _cell("Very likely") + _cell("4") + _cell("Major") + _cell("4"),
        # A merged cell spanning two columns: its continuation stays an empty cell.
        _cell("Unlikely|(rare)", gridSpan="2")
        + _cell("", hMerge="1")
        + _cell("Minor")
        + _cell("2"),
    ]
)


def _deck(*slides: str) -> bytes:
    files = {
        "[Content_Types].xml": "<Types/>",
        "ppt/presentation.xml": "<p:presentation xmlns:p='urn:p'/>",
    }
    for number, body in enumerate(slides, 1):
        files[f"ppt/slides/slide{number}.xml"] = (
            f"<p:sld {NS}><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>"
        )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _extract(tmp_path, content: bytes, version: str):
    path = tmp_path / "deck.pptx"
    path.write_bytes(content)
    return extract_document(
        path, PPTX, "deck", extract_settings(config_version=version)
    )


def test_v4_reads_slide_tables_in_place_with_their_slide(tmp_path):
    content = _deck(
        _shape("Risk assessment"),
        _shape("Risk matrix") + RATINGS + _shape("Low risk is 1 to 6"),
    )
    document, version = _extract(tmp_path, content, "layout-ocr-v4")
    assert version == "formats-v3"
    assert [(block.type, block.page_number) for block in document.blocks] == [
        ("paragraph", 1),
        ("paragraph", 2),
        ("table", 2),
        ("paragraph", 2),
    ]
    table = document.blocks[2]
    assert "| Probability | Rating | Severity of impact | Rating |" in table.text
    assert "| Very likely | 4 | Major | 4 |" in table.text
    assert "| Unlikely (rare) |  | Minor | 2 |" in table.text
    assert table.attributes["table"]["table_id"] == "s2-t1"
    assert table.attributes["table"]["slide"] == 2
    assert table.attributes["table"]["header_row"] == [
        "Probability",
        "Rating",
        "Severity of impact",
        "Rating",
    ]
    assert document.measurements.table_count == 1
    # Text shapes keep their numbering across the table frame.
    assert [block.attributes.get("shape") for block in document.blocks] == [
        1,
        1,
        None,
        2,
    ]


def test_v3_slide_output_is_unchanged(tmp_path):
    content = _deck(_shape("Risk matrix") + RATINGS + _shape("Low risk is 1 to 6"))
    v3, v3_version = _extract(tmp_path, content, "layout-ocr-v3")
    v4, _ = _extract(tmp_path, content, "layout-ocr-v4")
    assert v3_version == "formats-v2"
    assert all(block.type == "paragraph" for block in v3.blocks)
    assert "Very likely" not in "\n".join(block.text for block in v3.blocks)
    paragraphs = [block for block in v4.blocks if block.type == "paragraph"]
    assert [(b.text, b.attributes) for b in paragraphs] == [
        (b.text, b.attributes) for b in v3.blocks
    ]


def test_an_empty_slide_table_adds_no_block(tmp_path):
    content = _deck(_shape("Agenda") + _table([_cell("") + _cell("")]))
    document, _ = _extract(tmp_path, content, "layout-ocr-v4")
    assert [block.type for block in document.blocks] == ["paragraph"]


def test_a_slide_table_beyond_the_column_limit_fails_safely(tmp_path):
    content = _deck(_table(["".join(_cell(str(index)) for index in range(1_001))]))
    with pytest.raises(IngestionStageError) as error:
        _extract(tmp_path, content, "layout-ocr-v4")
    assert error.value.code == "table_limit"
