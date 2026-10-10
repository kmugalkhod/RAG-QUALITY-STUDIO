"""layout-ocr-v4 (spec 0008, B1): pages whose text runs sideways read row by row."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.ingestion_content.extractors import pdf as extraction
from app.ingestion_content.processing import processing_identity
from app.schemas.ingestion import ExtractNodeV2
from extract_corpus import extract, extract_settings, output_digests
from test_extract_v3_tables import LABELS, V2_VALUES, V3_VALUES, _Finder

HEADER = ["Year", "Households", "Median", "Mean"]
ROWS = [
    [str(2022 - index), f"{131 - index},400", f"{74 + index},580", f"{106 + index},400"]
    for index in range(8)
]
COLUMNS = [60.0, 170.0, 300.0, 430.0]
TITLE = "Table A-2. Households by Total Money Income: 2015 to 2022"


def _sideways_pdf(path: Path, *, reads_upward: bool) -> None:
    """A portrait page with a landscape table printed one cell at a time.

    Positions are planned on the landscape page a reader sees (792 x 612) and mapped
    onto the portrait page, as in Census P60-279 pp. 22-36.
    """

    document = pymupdf.open()
    page = document.new_page(width=612, height=792)

    def point(x: float, y: float) -> tuple[float, float]:
        return (y, 792 - x) if reads_upward else (612 - y, x)

    def put(x: float, y: float, text: str) -> None:
        page.insert_text(
            point(x, y), text, fontsize=9, rotate=90 if reads_upward else 270
        )

    put(60, 60, TITLE)
    for column, label in zip(COLUMNS, HEADER):
        put(column, 110, label)
    for row_index, row in enumerate(ROWS):
        for column, value in zip(COLUMNS, row):
            put(column, 130 + row_index * 16, value)
    document.save(path)


def _text(document) -> str:
    return "\n".join(block.text for block in document.blocks)


@pytest.mark.parametrize("reads_upward", [True, False])
def test_v4_reads_sideways_text_in_reading_order(tmp_path, reads_upward):
    path = tmp_path / "sideways.pdf"
    _sideways_pdf(path, reads_upward=reads_upward)
    document = extract(
        path, "application/pdf", extract_settings(config_version="layout-ocr-v4")
    )
    words = _text(document).split()
    expected = TITLE.split() + HEADER + [cell for row in ROWS for cell in row]
    assert words == expected
    page = document.pages[0]
    assert page.origin == "layout"
    assert page.rotation_degrees == (270 if reads_upward else 90)


def _sideways_merged_table_pdf(path: Path, turn: int) -> None:
    """The v3 borderless Census table on a landscape page, printed sideways."""

    source = pymupdf.open()
    landscape = source.new_page(width=792, height=612)
    landscape.insert_text((60, 104), "Characteristic", fontsize=9)
    landscape.insert_text((306, 104), "2021", fontsize=9)
    landscape.insert_text((426, 104), "2022", fontsize=9)
    for index, label in enumerate(LABELS):
        y = 128 + index * 20
        landscape.insert_text((60, y), label + " " + ". " * 12, fontsize=9)
        landscape.insert_text((306, y), V2_VALUES[index], fontsize=9)
        landscape.insert_text((426, y), V3_VALUES[index], fontsize=9)
    document = pymupdf.open()
    portrait = document.new_page(width=612, height=792)
    portrait.show_pdf_page(portrait.rect, source, 0, rotate=turn)
    document.save(path)


@pytest.mark.parametrize("turn", [90, 270])
def test_v4_rebuilds_a_sideways_merged_table_row_by_row(tmp_path, monkeypatch, turn):
    path = tmp_path / "sideways-table.pdf"
    _sideways_merged_table_pdf(path, turn)
    # PyMuPDF reports the Census table as one cell per column (see the v3 tests).
    monkeypatch.setattr(pymupdf.Page, "find_tables", lambda self, *a, **k: _Finder())
    married = f"Married-couple {V2_VALUES[2]} {V3_VALUES[2]}"

    v4 = extract(
        path, "application/pdf", extract_settings(config_version="layout-ocr-v4")
    )
    tables = [block for block in v4.blocks if block.type == "table"]
    lines = "\n".join(block.text for block in tables).splitlines()
    assert lines[0] == "Characteristic 2021 2022"
    assert married in lines
    assert tables[0].attributes["table"]["reconstruction"] == "word-rows"
    assert v4.pages[0].rotation_degrees in (90, 270)

    v3 = extract(
        path, "application/pdf", extract_settings(config_version="layout-ocr-v3")
    )
    assert married not in "\n".join(block.text for block in v3.blocks).splitlines()
    assert v3.pages[0].rotation_degrees == 0


@pytest.mark.parametrize("reads_upward", [True, False])
def test_v4_boxes_point_at_the_text_on_the_original_page(tmp_path, reads_upward):
    path = tmp_path / "sideways.pdf"
    _sideways_pdf(path, reads_upward=reads_upward)
    document = extract(
        path, "application/pdf", extract_settings(config_version="layout-ocr-v4")
    )
    with pymupdf.open(path) as source:
        page = source[0]
        title_words = [w for w in page.get_text("words") if w[4] == "Table"]
    assert len(title_words) == 1
    x0, y0, x1, y1 = title_words[0][:4]
    centre = ((x0 + x1) / 2 / 612, (y0 + y1) / 2 / 792)
    title_block = next(block for block in document.blocks if TITLE in block.text)
    box = title_block.bounding_box
    assert box is not None
    assert box.left <= centre[0] <= box.right
    assert box.top <= centre[1] <= box.bottom
    # A sideways line is tall and narrow on the portrait page.
    assert box.bottom - box.top > box.right - box.left


def test_v3_reads_a_sideways_page_without_straightening(tmp_path):
    path = tmp_path / "sideways.pdf"
    _sideways_pdf(path, reads_upward=True)
    v3 = extract(
        path, "application/pdf", extract_settings(config_version="layout-ocr-v3")
    )
    assert v3.pages[0].rotation_degrees == 0
    words = _text(v3).split()
    assert words != TITLE.split() + HEADER + [cell for row in ROWS for cell in row]


def test_v4_matches_v3_on_upright_pages(tmp_path):
    (tmp_path / "v3").mkdir()
    (tmp_path / "v4").mkdir()
    assert output_digests(tmp_path / "v4", config_version="layout-ocr-v4") == (
        output_digests(tmp_path / "v3", config_version="layout-ocr-v3")
    )


def test_mostly_upright_pages_are_not_straightened():
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    for index in range(30):
        page.insert_text((72, 72 + index * 20), f"Upright line {index} of body text.")
    page.insert_text((560, 700), "Sideways page label", rotate=90)
    assert extraction._sideways_rotation(page) == 0


def test_unrotated_box_inverts_both_turns():
    box = extraction.BoundingBox(left=0.1, top=0.2, right=0.4, bottom=0.3)
    upward = extraction._unrotated_box(box, 270)
    assert (upward.left, upward.top, upward.right, upward.bottom) == pytest.approx(
        (0.2, 0.6, 0.3, 0.9)
    )
    downward = extraction._unrotated_box(box, 90)
    assert (downward.left, downward.top, downward.right, downward.bottom) == (
        pytest.approx((0.7, 0.1, 0.8, 0.4))
    )
    assert extraction._unrotated_box(None, 90) is None


def test_v4_schema_version_and_identity():
    v4 = ExtractNodeV2(
        id="extract", type="extract", strategy="auto", config_version="layout-ocr-v4"
    )
    assert extraction.extractor_version_for_settings(v4) == (
        extraction.LAYOUT_OCR_V4_EXTRACTOR_VERSION
    )
    assert len(extraction.LAYOUT_OCR_V4_EXTRACTOR_VERSION) <= 120

    def identity(version):
        node = extract_settings(config_version=version)
        return processing_identity(
            schema_version=2,
            extractor_version=extraction.extractor_version_for_settings(node),
            cleaner_version="c",
            chunker_version="k",
            extract=node.model_dump(mode="json", exclude={"id", "type"}),
            clean={},
            chunk={},
        )[1]

    assert identity("layout-ocr-v3") != identity("layout-ocr-v4")
