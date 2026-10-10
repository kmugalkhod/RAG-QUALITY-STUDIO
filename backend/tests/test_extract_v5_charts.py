"""layout-ocr-v5 (spec 0009, Part A): a chart's gridlines are not a table.

The French Eurostat report (spec 0008, A2) has bar charts whose gridlines PyMuPDF's
table finder reads as tables of 52-57 mostly empty columns. v4 counts them as
malformed tables, which stops the file under the default policy, and drops the
chart's callout text. The synthetic page below has the same shape: a 55-column
chart grid with a callout, axis ticks and country codes, beside a real table.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pymupdf
import pytest

from app.ingestion_content.extractors import extract_document
from app.ingestion_content.extractors import pdf as extraction
from app.services.website_ingestion import uses_v3_reading
from app.schemas.ingestion import ExtractNodeV2
from extract_corpus import extract_settings, output_digests

CALLOUT = "381 deaths per 100 000 inhabitants in the EU"
CODES = ["BG", "RO", "LT", "LV", "HU"]
TABLE_ROWS = [
    ["Country", "Deaths", "Rate"],
    ["Bulgaria", "1,133", "5.5"],
    ["France", "205", "1.0"],
    ["Lithuania", "1,010", "4.9"],
]


def _chart_page(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((40, 40), "Deaths from circulatory diseases", fontsize=12)
    # The chart: 55 narrow columns between gridlines, empty except a few labels.
    left, top, step, bottom = 40.0, 60.0, 9.0, 300.0
    for index in range(56):
        x = left + index * step
        page.draw_line((x, top), (x, bottom), width=0.3)
    for y in (top, 120.0, 180.0, 240.0, bottom):
        page.draw_line((left, y), (left + 55 * step, y), width=0.3)
    for index, code in enumerate(CODES):
        page.insert_text((left + index * step + 1, bottom - 4), code, fontsize=4)
    for y, tick in ((124.0, "1 500"), (184.0, "1 000"), (244.0, "500")):
        page.insert_text((left + 2, y), tick, fontsize=4)
    page.insert_text((left + 20 * step + 2, 100.0), CALLOUT, fontsize=7)
    # A real table: every cell filled.
    tx, ty, width, height = 600.0, 60.0, 70.0, 20.0
    for row_index in range(len(TABLE_ROWS) + 1):
        page.draw_line(
            (tx, ty + row_index * height), (tx + 3 * width, ty + row_index * height)
        )
    for column in range(4):
        page.draw_line(
            (tx + column * width, ty),
            (tx + column * width, ty + len(TABLE_ROWS) * height),
        )
    for row_index, row in enumerate(TABLE_ROWS):
        for column, value in enumerate(row):
            page.insert_text(
                (tx + column * width + 4, ty + row_index * height + 14),
                value,
                fontsize=8,
            )
    page.insert_text((40, 340), "Bulgaria had the highest rate in 2015.", fontsize=11)
    document.save(path)


@pytest.fixture
def chart_pdf(tmp_path) -> Path:
    path = tmp_path / "chart.pdf"
    _chart_page(path)
    return path


def _extract(path: Path, version: str):
    document, _ = extract_document(
        path, "application/pdf", "chart", extract_settings(config_version=version)
    )
    return document


def _text(document) -> str:
    return "\n".join(block.text for block in document.blocks)


def test_the_synthetic_chart_is_detected_as_a_sparse_table(chart_pdf):
    page = pymupdf.open(chart_pdf)[0]
    shapes = [
        (len(rows), max(len(row) for row in rows))
        for rows in (table.extract() for table in page.find_tables().tables)
    ]
    assert (4, 55) in shapes and (4, 3) in shapes


def test_v4_drops_the_callout_and_reports_a_malformed_table(chart_pdf):
    document = _extract(chart_pdf, "layout-ocr-v4")
    assert CALLOUT not in _text(document)
    assert document.measurements.malformed_table_count == 1
    assert any(
        f.code == "malformed_tables" and f.severity == "error"
        for f in document.findings
    )


def test_v5_reads_the_chart_as_text_and_keeps_the_real_table(chart_pdf):
    document = _extract(chart_pdf, "layout-ocr-v5")
    text = _text(document)
    callout = [block for block in document.blocks if CALLOUT in block.text]
    assert len(callout) == 1 and callout[0].type != "table"
    assert callout[0].attributes["chart_region"] is True
    assert document.measurements.malformed_table_count == 0
    assert document.measurements.table_count == 1
    tables = [block.text for block in document.blocks if block.type == "table"]
    assert any("Bulgaria" in table and "1,133" in table for table in tables)
    assert not any(f.code == "malformed_tables" for f in document.findings)
    assert "Bulgaria had the highest rate in 2015." in text


def test_all_chart_text_is_kept_and_only_chart_text_is_marked(chart_pdf):
    document = _extract(chart_pdf, "layout-ocr-v5")
    marked = " ".join(
        block.text for block in document.blocks if block.attributes.get("chart_region")
    ).split()
    # Data labels can be plain numbers, so ticks and codes are kept too (v4 kept
    # them inside its table block).
    for word in [*CALLOUT.split(), *CODES, "1", "500", "000"]:
        assert word in marked
    unmarked = " ".join(
        block.text
        for block in document.blocks
        if not block.attributes.get("chart_region")
    )
    assert CALLOUT not in unmarked and "Bulgaria had the highest" in unmarked


def test_v5_keeps_all_text_v4_read_on_the_page(chart_pdf):
    # v4 splits chart labels across cells ("1 000" becomes "00" and "0"), so compare
    # characters rather than words; table pipes and rules are layout, not text.
    def characters(document):
        return Counter(
            character
            for block in document.blocks
            for character in block.text
            if not character.isspace() and character not in "|-"
        )

    lost = characters(_extract(chart_pdf, "layout-ocr-v4")) - characters(
        _extract(chart_pdf, "layout-ocr-v5")
    )
    assert not lost


@pytest.mark.parametrize(
    ("filled", "chart"),
    [(0, True), (29, True), (30, False), (100, False)],
)
def test_the_fill_threshold(filled, chart):
    flat = ["x"] * filled + [""] * (100 - filled)
    grid = [flat[index * 10 : index * 10 + 10] for index in range(10)]
    assert extraction._is_chart_region(grid) is chart
    assert extraction._is_chart_region([]) is True
    assert extraction._is_chart_region([[None, " "], ["", None]]) is True


def test_v5_equals_v4_on_the_corpus_without_charts(tmp_path):
    (tmp_path / "v4").mkdir()
    (tmp_path / "v5").mkdir()
    assert output_digests(tmp_path / "v5", config_version="layout-ocr-v5") == (
        output_digests(tmp_path / "v4", config_version="layout-ocr-v4")
    )


def test_v5_identity_and_reading():
    settings = ExtractNodeV2.model_validate(
        {**extract_settings(config_version="layout-ocr-v5").model_dump(mode="json")}
    )
    version = extraction.extractor_version_for_settings(settings)
    assert "/layout-v5/formats-v3" in version and len(version) <= 120
    assert uses_v3_reading(settings)
    for frozen in ("layout-ocr-v2", "layout-ocr-v3", "layout-ocr-v4"):
        assert frozen not in extraction.CHART_REGION_VERSIONS


@pytest.mark.parametrize(
    ("box", "share"),
    [
        ((10, 10, 20, 20), 1.0),  # inside the chart
        ((90, 10, 110, 20), 0.5),  # half inside
        ((200, 200, 210, 210), 0.0),  # outside
        ((10, 10, 10, 20), 0.0),  # no area
    ],
)
def test_overlap_share(box, share):
    assert extraction._overlap_share(box, (0, 0, 100, 100)) == share
