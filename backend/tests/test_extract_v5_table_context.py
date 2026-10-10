"""layout-ocr-v5 (spec 0009, Part B): tables keep their caption and header.

In spec 0008's round A2 the sideways Census Table A-2 rows were extracted correctly
but not retrieved: their section path was "... > Endnotes" (a heading that ran on
from an earlier page), the caption "Table A-2. ..." was a plain paragraph, and
the rebuilt rows repeated only the first header line.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.ingestion_content import CanonicalInputSegment
from app.ingestion_content.extractors import extract_document
from app.ingestion_content.extractors import pdf as extraction
from extract_corpus import extract_settings

CENSUS_LINES = [
    "Race and Hispanic origin of Percent distribution Median income Mean income",
    "householder Number $15,000 $25,000 $35,000",
    "(thou- Under to to to Margin of Margin of",
    "and year sands) Total $15,000 $24,999 $34,999 Estimate error (±) Estimate error (±)",
    "ALL RACES",
    "2022 131,400 100 8.3 7.4 7.6 74,580 968 106,400 1,034",
    "2021 131,200 100 8.4 7.7 7.5 76,330 653 110,300 1,110",
]


def test_header_lines_stop_at_the_first_data_line():
    # Currency column ranges are header text, and the section label stays a row.
    assert extraction._header_line_count(CENSUS_LINES) == 4


@pytest.mark.parametrize(
    ("lines", "count"),
    [
        (["Year Median Mean", "2022 74,580 106,400"], 1),
        (["2022 74,580 106,400", "2021 76,330 110,300"], 0),
        (["Only words here", "And more words"], 0),
        ([f"Header line {index}" for index in range(9)] + ["2022 1 2 3"], 0),
    ],
)
def test_header_line_count_edges(lines, count):
    assert extraction._header_line_count(lines) == count


@pytest.mark.parametrize(
    ("text", "caption"),
    [
        ("Table A-2.\nHouseholds by Total Money Income", True),
        ("Table 1: GLUE results", True),
        ("Table A-4a.\nSelected Measures of Household Income Dispersion", True),
        ("Table 2b Results", True),
        ("Table 3.1 Summary", True),
        ("Tableau II. Population", True),
        ("TABLE 1.--ESTIMATED WITHDRAWAL USE OF WATER", True),
        ("Table of contents", False),
        ("Tables show the results", False),
        ("The table below lists", False),
    ],
)
def test_caption_pattern(text, caption):
    assert bool(extraction._TABLE_CAPTION.match(text)) is caption


def _segment(text, page, block_type="paragraph", path=(), table_id=None):
    attributes = {"table": {"table_id": table_id}} if table_id else {}
    return CanonicalInputSegment(
        text=text,
        page_number=page,
        block_type=block_type,
        heading_path=path,
        attributes=attributes,
    )


def test_caption_joins_the_table_path_and_replaces_a_run_on_heading():
    appendix = ("Report", "APPENDIX A", "Endnotes")
    segments = [
        _segment("Endnotes", 1, "heading", ("Report", "APPENDIX A")),
        _segment("1 A note.", 1, path=appendix),
        _segment(
            "Table A-2.\nHouseholds by Income: 1967 to 2022\n(Income in 2022 dollars.)",
            2,
            path=appendix,
        ),
        _segment("rows 1", 2, "table", appendix, "p2-t1"),
        _segment("rows 2", 2, "table", appendix, "p2-t1"),
        _segment("16 Income in the United States", 2, path=appendix),
    ]
    result = extraction._table_captions(segments)
    caption = "Table A-2. Households by Income: 1967 to 2022"
    expected = ("Report", "APPENDIX A", caption)
    assert [segment.heading_path for segment in result[2:5]] == [expected] * 3
    assert result[3].attributes["table"]["caption"] == caption
    # Blocks that are not the caption or its table keep their path.
    assert result[1].heading_path == appendix
    assert result[5].heading_path == appendix


def test_a_heading_on_the_same_page_stays_in_the_path():
    section = ("Paper", "Results")
    segments = [
        _segment("Results", 3, "heading", ("Paper",)),
        _segment("Table 2: Scores", 3, path=section),
        _segment("| a | b |", 3, "table", section, "p3-t1"),
    ]
    result = extraction._table_captions(segments)
    assert result[2].heading_path == ("Paper", "Results", "Table 2: Scores")


def test_a_section_heading_from_an_earlier_page_stays_in_the_path():
    # A section's table can sit pages after its heading; only notes or references
    # headings are treated as run-on.
    section = ("Paper", "Results")
    segments = [
        _segment("Results", 5, "heading", ("Paper",)),
        _segment("Table 2: Scores", 7, path=section),
        _segment("| a | b |", 7, "table", section, "p7-t1"),
    ]
    result = extraction._table_captions(segments)
    assert result[2].heading_path == ("Paper", "Results", "Table 2: Scores")


@pytest.mark.parametrize(
    "heading",
    ["Endnotes", "ENDNOTES", "Notes", "References", "Sources", "Notes et sources"],
)
def test_back_matter_headings(heading):
    assert extraction._BACK_MATTER_HEADING.match(heading)


@pytest.mark.parametrize(
    "heading", ["Results", "Notes on method", "Income sources by state"]
)
def test_section_headings_are_not_back_matter(heading):
    assert not extraction._BACK_MATTER_HEADING.match(heading)


def test_a_caption_without_a_table_after_it_on_the_page_is_left_alone():
    segments = [
        _segment("Table 1: Results", 1, path=("Paper",)),
        _segment("A paragraph.", 1, path=("Paper",)),
        _segment("Table 2: More", 1, path=("Paper",)),
        _segment("| a |", 2, "table", ("Paper",), "p2-t1"),
    ]
    assert extraction._table_captions(segments) == segments


def test_only_the_first_table_after_a_caption_takes_it():
    segments = [
        _segment("Table 1: First", 1),
        _segment("| a |", 1, "table", (), "p1-t1"),
        _segment("| b |", 1, "table", (), "p1-t2"),
    ]
    result = extraction._table_captions(segments)
    assert result[1].heading_path == ("Table 1: First",)
    assert result[2].heading_path == ()


CAPTION = "Table A-2. Households by Total Money Income: 2015 to 2022"


def _appendix_pdf(path: Path) -> None:
    """An appendix like Census P60-279: a heading, then a captioned table a page on."""

    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((72, 72), "Appendix A. Estimates of Income", fontsize=18)
    first.insert_text((72, 110), "Endnotes", fontsize=14)
    for index, note in enumerate(
        [
            "1 Estimates are in 2022 dollars, adjusted for price changes.",
            "2 Households are counted as of March of the following year.",
            "3 Medians are calculated from grouped income distributions.",
            "4 Margins of error are given at the 90 percent confidence level.",
        ]
    ):
        first.insert_text((72, 140 + index * 14), note, fontsize=10)
    second = document.new_page()
    second.insert_text((72, 60), CAPTION, fontsize=10)
    second.insert_text((72, 74), "(Income in 2022 dollars.)", fontsize=10)
    rows = [
        ["Year", "Median", "Mean"],
        ["2022", "74,580", "106,400"],
        ["2021", "76,330", "110,300"],
        ["2015", "68,410", "95,950"],
    ]
    left, top, width, height = 72.0, 90.0, 90.0, 20.0
    for index in range(len(rows) + 1):
        second.draw_line(
            (left, top + index * height), (left + 3 * width, top + index * height)
        )
    for column in range(4):
        second.draw_line(
            (left + column * width, top),
            (left + column * width, top + len(rows) * height),
        )
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            second.insert_text(
                (left + column * width + 4, top + row_index * height + 14),
                value,
                fontsize=10,
            )
    document.save(path)


def test_v5_files_a_captioned_table_under_its_caption(tmp_path):
    path = tmp_path / "appendix.pdf"
    _appendix_pdf(path)
    documents = {
        version: extract_document(
            path, "application/pdf", "a", extract_settings(config_version=version)
        )[0]
        for version in ("layout-ocr-v4", "layout-ocr-v5")
    }
    v4_table = next(b for b in documents["layout-ocr-v4"].blocks if b.type == "table")
    v5_table = next(b for b in documents["layout-ocr-v5"].blocks if b.type == "table")
    assert "68,410" in v5_table.text
    # v4 files the table under the heading that ran on from page 1.
    assert v4_table.heading_path[-1] == "Endnotes"
    assert v5_table.heading_path[-1] == CAPTION
    assert "Endnotes" not in v5_table.heading_path
    assert v5_table.attributes["table"]["caption"] == CAPTION
    # Only the context changes, not the text.
    assert [b.text for b in documents["layout-ocr-v5"].blocks] == [
        b.text for b in documents["layout-ocr-v4"].blocks
    ]


def test_table_context_is_v5_only():
    for frozen in ("layout-ocr-v2", "layout-ocr-v3", "layout-ocr-v4"):
        assert frozen not in extraction.TABLE_CONTEXT_VERSIONS
    assert "layout-ocr-v5" in extraction.TABLE_CONTEXT_VERSIONS
