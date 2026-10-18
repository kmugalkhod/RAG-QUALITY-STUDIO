"""layout-ocr-v6 (spec 0014, Part A): table rows are kept and columns are named.

GAO-23-900494 Table 2 is found by PyMuPDF as two small ruled "tables" (the header
and the Total row); the rows between them are text blocks. v5 dropped every block
that touched a table box, so the Inhofe row, starting 0.00001 points inside the
header box, was lost. Census Table A-2 is rebuilt from word rows, and v5 kept each
printed row as one line without saying which number is which.
"""

from __future__ import annotations

from app.ingestion_content.extractors import pdf as extraction


def _line(box, text):
    return {"bbox": box, "spans": [{"text": text}]}


def test_only_lines_mostly_inside_a_table_are_dropped():
    header = (219.6, 447.65, 576.4, 466.2)
    block = {
        "type": 0,
        "bbox": (223.2, 455.85, 574.62, 485.53),
        "lines": [
            _line((557.28, 455.85, 574.62, 467.28), "FTE "),
            _line((223.2, 465.46, 268.98, 476.35), "P.L 117-263 "),
            _line((282.6, 465.46, 407.53, 476.35), "James M. Inhofe National Defense "),
        ],
    }
    kept = extraction._outside_tables(block, [header])
    assert [line["spans"][0]["text"] for line in kept["lines"]] == [
        "P.L 117-263 ",
        "James M. Inhofe National Defense ",
    ]
    assert kept["bbox"] == (223.2, 465.46, 407.53, 476.35)


def test_a_row_touching_a_header_box_by_a_hair_is_kept():
    header = (36.71, 184.47, 574.88, 208.73999)
    block = {
        "type": 0,
        "bbox": (38.88, 208.7399, 578.2, 221.02),
        "lines": [
            _line((38.88, 208.7399, 578.2, 221.02), "P.L 117-263 Inhofe 158 312")
        ],
    }
    assert extraction._outside_tables(block, [header]) == block


def test_blocks_away_from_tables_are_returned_unchanged_and_inside_ones_dropped():
    table = (100.0, 100.0, 300.0, 200.0)
    away = {"type": 0, "bbox": (10.0, 10.0, 90.0, 20.0), "lines": []}
    inside = {
        "type": 0,
        "bbox": (110.0, 110.0, 200.0, 120.0),
        "lines": [_line((110.0, 110.0, 200.0, 120.0), "cell")],
    }
    assert extraction._outside_tables(away, [table]) is away
    assert extraction._outside_tables(inside, [table]) is None


class _Words:
    """A page stand-in that returns fixed word boxes."""

    def __init__(self, lines):
        self.words = [
            (left, y - 4.0, right, y + 4.0, text)
            for y, words in lines
            for left, right, text in words
        ]

    def get_text(self, kind, clip=None):
        assert kind == "words"
        return list(self.words)


def _census(rows=3):
    lines = [
        (100.0, [(72, 90, "Race"), (594, 618, "Median"), (620, 645, "income")]),
        (
            110.0,
            [
                (72, 85, "and"),
                (87, 105, "year"),
                (157, 185, "Number"),
                (208, 224, "Total"),
                (588, 618, "Estimate"),
                (625, 648, "Margin"),
            ],
        ),
        (125.0, [(72, 86, "ALL"), (88, 112, "RACES")]),
    ]
    values = [
        ("2022.", "131,400", "74,580", "968"),
        ("20202.", "129,200", "76,660", "992"),
        ("2015.", "125,800", "68,410", "639"),
        ("2014.", "124,600", "64,900", "780"),
    ]
    for index, (year, number, median, margin) in enumerate(values[:rows]):
        lines.append(
            (
                135.0 + 10 * index,
                [
                    (72, 91 if len(year) == 5 else 94, year),
                    (96, 99, "."),
                    (143, 185, number),
                    (212, 224, "100"),
                    (594, 618, median),
                    (644, 657, margin),
                ],
            )
        )
    return _Words(lines)


def test_word_columns_name_every_column_and_keep_group_labels():
    grid = extraction._word_columns(_census(rows=4), (72, 95, 740, 200))
    assert grid[0] == [
        "Race and year",
        "Number",
        "Total",
        "Median income Estimate",
        "Median income Margin",
    ]
    assert grid[1] == ["ALL RACES", "", "", "", ""]
    assert grid[4] == ["2015", "125,800", "100", "68,410", "639"]
    # Footnote marks printed after a year stay, as in v5.
    assert grid[3][0] == "20202"


def test_word_columns_need_three_data_lines():
    assert extraction._word_columns(_census(rows=2), (72, 95, 740, 200)) is None


def test_word_columns_respect_the_word_bound(monkeypatch):
    monkeypatch.setattr(extraction, "MAX_WORD_COLUMN_WORDS", 10)
    assert extraction._word_columns(_census(rows=4), (72, 95, 740, 200)) is None


def test_header_words_broken_with_a_hyphen_are_rejoined():
    assert extraction._joined_header(["Number", "(thou-", "sands)"]) == (
        "Number (thousands)"
    )
    assert extraction._joined_header(["(thou­", "sands)"]) == "(thousands)"
    assert extraction._joined_header(["Non-", "Hispanic"]) == "Non- Hispanic"


def test_v6_is_its_own_version_and_v5_is_unchanged():
    from types import SimpleNamespace

    def version(value):
        return extraction.extractor_version_for_settings(
            SimpleNamespace(config_version=value)
        )

    assert "/layout-v6/" in version("layout-ocr-v6")
    assert "/layout-v5/" in version("layout-ocr-v5")
    assert "layout-ocr-v5" not in extraction.TABLE_ROW_VERSIONS
