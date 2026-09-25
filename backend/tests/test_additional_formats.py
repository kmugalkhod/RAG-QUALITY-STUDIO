"""Synthetic fixtures for every explicitly released structured-file adapter."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.ingestion_content.extractors import extract_document
from app.ingestion_content.extractors.formats import (
    CSV,
    DOCX,
    HTML,
    MARKDOWN,
    PPTX,
    TSV,
    XLSX,
)
from app.ingestion_content.processing import IngestionStageError
from app.schemas.ingestion import ExtractNodeV2


def _package(files: dict[str, str | bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _extract(tmp_path, name: str, content: bytes, media_type: str):
    path = tmp_path / name
    path.write_bytes(content)
    settings = ExtractNodeV2(
        id="extract",
        type="extract",
        strategy="auto",
        config_version="layout-ocr-v1",
        quality_policy="default-v1",
    )
    return extract_document(path, media_type, name, settings)[0]


@pytest.mark.parametrize(
    ("name", "media_type", "content", "expected_type", "expected"),
    [
        (
            "guide.md",
            MARKDOWN,
            b"# Guide\n\nIntro text.\n\n- First item\n\n```py\nprint('safe')\n```\n",
            "heading",
            "Guide",
        ),
        (
            "page.html",
            HTML,
            b"<!doctype html><html><body><script>secret()</script><h1>Title</h1><p>Safe body</p></body></html>",
            "heading",
            "Safe body",
        ),
        ("table.csv", CSV, b"name,value\nalpha,1\nbeta,2\n", "table", "alpha"),
        ("table.tsv", TSV, b"name\tvalue\nalpha\t1\n", "table", "alpha"),
    ],
)
def test_text_structured_adapters(
    tmp_path, name, media_type, content, expected_type, expected
):
    document = _extract(tmp_path, name, content, media_type)
    assert document.media_type == media_type
    assert any(block.type == expected_type for block in document.blocks)
    assert expected in "\n".join(block.text for block in document.blocks)
    assert "secret()" not in "\n".join(block.text for block in document.blocks)


def test_docx_maps_headings_paragraphs_and_tables(tmp_path):
    content = _package(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": """
                <w:document xmlns:w="urn:w"><w:body>
                  <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Policy</w:t></w:r></w:p>
                  <w:p><w:r><w:t>Reviewed body</w:t></w:r></w:p>
                  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
                </w:body></w:document>
            """,
        }
    )
    document = _extract(tmp_path, "policy.docx", content, DOCX)
    assert [block.type for block in document.blocks] == [
        "heading",
        "paragraph",
        "table",
    ]
    assert document.blocks[1].heading_path == ["Policy"]


def test_pptx_preserves_slide_provenance(tmp_path):
    content = _package(
        {
            "[Content_Types].xml": "<Types/>",
            "ppt/presentation.xml": "<p:presentation xmlns:p='urn:p'/>",
            "ppt/slides/slide1.xml": "<p:sld xmlns:p='urn:p' xmlns:a='urn:a'><p:sp><a:p><a:r><a:t>Slide one</a:t></a:r></a:p></p:sp></p:sld>",
            "ppt/slides/slide2.xml": "<p:sld xmlns:p='urn:p' xmlns:a='urn:a'><p:sp><a:p><a:r><a:t>Slide two</a:t></a:r></a:p></p:sp></p:sld>",
        }
    )
    document = _extract(tmp_path, "slides.pptx", content, PPTX)
    assert [block.page_number for block in document.blocks] == [1, 2]
    assert document.blocks[1].text == "Slide two"


def test_xlsx_preserves_sheet_rows_and_never_evaluates_formulas(tmp_path):
    content = _package(
        {
            "[Content_Types].xml": "<Types/>",
            "xl/workbook.xml": "<workbook/>",
            "xl/sharedStrings.xml": "<sst xmlns='urn:x'><si><t>Name</t></si><si><t>Alpha</t></si></sst>",
            "xl/worksheets/sheet1.xml": """
                <worksheet xmlns="urn:x"><sheetData>
                  <row r="1"><c t="s"><v>0</v></c><c><v>Value</v></c></row>
                  <row r="2"><c t="s"><v>1</v></c><c><f>1+1</f><v>2</v></c></row>
                </sheetData></worksheet>
            """,
        }
    )
    document = _extract(tmp_path, "book.xlsx", content, XLSX)
    assert len(document.blocks) == 2
    assert "Alpha" in document.blocks[1].text
    assert "=1+1" in document.blocks[1].text


def test_package_mismatch_macro_and_compression_limits_fail_safely(tmp_path):
    docx = _package(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<w:document xmlns:w='urn:w'><w:body><w:p><w:r><w:t>Text</w:t></w:r></w:p></w:body></w:document>",
        }
    )
    with pytest.raises(IngestionStageError, match="stored media type"):
        _extract(tmp_path, "wrong.pptx", docx, PPTX)

    macro = _package(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<w:document xmlns:w='urn:w'><w:body><w:p><w:r><w:t>Text</w:t></w:r></w:p></w:body></w:document>",
            "word/vbaProject.bin": b"synthetic-not-executable",
        }
    )
    with pytest.raises(IngestionStageError, match="Macro-enabled"):
        _extract(tmp_path, "macro.docx", macro, DOCX)

    bomb = _package(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "A" * 1_000_000,
        }
    )
    with pytest.raises(IngestionStageError, match="violates"):
        _extract(tmp_path, "bomb.docx", bomb, DOCX)

    with pytest.raises(IngestionStageError, match="could not be parsed"):
        _extract(tmp_path, "broken.csv", b'name,value\n"unterminated,1\n', CSV)
