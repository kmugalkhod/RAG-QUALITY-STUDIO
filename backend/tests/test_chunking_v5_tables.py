"""Spec 0015 S3: section-token-v5 and parent-child-v5 keep each table's v3 passage
beside its row passages, and read a title row above a table's real header."""

from app.ingestion_content import CanonicalInputSegment
from app.ingestion_content.tables import table_row_groups
from test_chunking_v4_rows import (
    ROWS,
    _chunks,
    _cleaned,
    _parent_child,
    _section,
    _table,
)
from app.ingestion_content import chunk_cleaned_document

INTRO = CanonicalInputSegment(
    text="Table A-2.\nHouseholds by Total Money Income",
    block_type="paragraph",
    page_number=1,
    heading_path=("APPENDIX A", "Table A-2. Households by Total Money Income"),
)


def _rows(chunks):
    return [c for c in chunks if c.provenance.get("table_passage")]


def _others(chunks):
    return [c for c in chunks if not c.provenance.get("table_passage")]


def _same(left, right):
    keys = ("text", "embedding_text", "chunk_role", "page_number", "token_count")
    return [tuple(getattr(c, k) for k in keys) for c in left] == [
        tuple(getattr(c, k) for k in keys) for c in right
    ]


def test_section_token_v5_keeps_the_v3_table_passage_and_adds_row_passages():
    segments = [INTRO, *_table(ROWS)]
    v3 = _chunks(segments, _section("section-token-v3"))
    v4 = _chunks(segments, _section("section-token-v4"))
    v5 = _chunks(segments, _section("section-token-v5"))
    # Every v3 passage is still there, in order, unchanged.
    assert _same(_others(v5), v3)
    assert any("| 2015 | 125,800 | 68,410 |" in c.text for c in _others(v5))
    # The rows are the v4 row passages (no title row here), marked row-v2.
    assert [c.embedding_text for c in _rows(v5)] == [
        c.embedding_text for c in _rows(v4)
    ]
    assert {c.provenance["table_passage"] for c in _rows(v5)} == {"row-v2"}
    assert {c.provenance["table_passage"] for c in _rows(v4)} == {"row-v1"}
    assert "Race and year: 2015; Number (thousands): 125,800" in (
        _rows(v5)[0].embedding_text
    )
    assert all(c.chunk_role == "leaf" for c in v5)
    # Each row passage follows the passage that holds its table.
    table_at = next(
        i for i, c in enumerate(v5) if "| 2015 | 125,800" in c.text and c in _others(v5)
    )
    first_row = next(i for i, c in enumerate(v5) if c in _rows(v5))
    assert first_row == table_at + 1
    assert [c.ordinal for c in v5] == list(range(len(v5)))


def test_parent_child_v5_keeps_v3_parents_and_children_and_adds_row_children():
    segments = [INTRO, *_table(ROWS)]
    v3 = _chunks(segments, _parent_child("parent-child-v3"))
    v4 = _chunks(segments, _parent_child("parent-child-v4"))
    v5 = _chunks(segments, _parent_child("parent-child-v5"))
    assert _same(_others(v5), v3)
    rows = _rows(v5)
    # One per data row; label rows open the rows below them.
    assert [c.embedding_text for c in rows] == [c.embedding_text for c in _rows(v4)]
    assert len(rows) == 3
    parents = {c.ordinal: c for c in v5 if c.chunk_role == "parent"}
    for row in rows:
        assert row.chunk_role == "child"
        # The parent holds the row's line, so the prompt gets the whole table.
        row_line = row.text.splitlines()[-1]
        assert row_line in parents[row.parent_ordinal].text
    assert [c.ordinal for c in v5] == list(range(len(v5)))


def test_a_list_across_rows_is_still_one_passage_in_v5():
    # DfT f6-q2: the answer spans several rows; v4 split it into one passage per row.
    rows = [
        ["Carriageways", "1", "2"],
        ["Footways", "3", "4"],
        ["Drainage", "5", "6"],
        ["Street lighting", "7", "8"],
    ]
    segments = [INTRO, *_table(rows)]
    v4 = _chunks(segments, _section("section-token-v4"))
    v5 = _chunks(segments, _section("section-token-v5"))
    whole = [c for c in v5 if "Drainage" in c.text and "Street lighting" in c.text]
    assert whole and not _rows(whole)
    assert not [c for c in v4 if "Drainage" in c.text and "Street lighting" in c.text]


TITLE = "Economic Inactivity by Sex, Aged 16 to 64 [Notes 18, 19]"
NISRA = [
    [TITLE, "", "", ""],
    ["Source: Labour Force Survey, October to December, 2012 to 2023", "", "", ""],
    ["Time period", "Males", "Females", "All persons"],
    ["Oct to Dec 2022", "22.7", "32", "27.4"],
    ["Oct to Dec 2023", "22", "31.7", "26.9"],
]


def _sheet(rows, version):
    groups, _ = table_row_groups(
        rows,
        "preserve",
        table_id="sheet-1",
        max_rows=2000,
        max_columns=50,
        max_cell_characters=None,
        base_attributes={"origin": "spreadsheet", "engine": "openpyxl"},
    )
    segments = [
        CanonicalInputSegment(
            text=evidence,
            block_type="table",
            page_number=None,
            heading_path=("6.3 Inactivity rates",),
            attributes=attributes,
        )
        for evidence, attributes, _, _ in groups
    ]
    settings = (
        _section(version) if version.startswith("section") else _parent_child(version)
    )
    return chunk_cleaned_document(_cleaned(segments), settings).chunks


def test_v5_takes_the_header_from_the_row_below_a_title_row():
    rows = _rows(_sheet(NISRA, "section-token-v5"))
    searched = {c.embedding_text.split("\n\n", 1)[-1] for c in rows}
    assert (
        f"{TITLE}. Time period: Oct to Dec 2023; Males: 22; Females: 31.7; "
        "All persons: 26.9"
    ) in searched
    assert len(rows) == 2
    passage = next(c for c in rows if "Oct to Dec 2023" in c.text)
    # The passage shows the title, the note and the header above the row.
    assert TITLE in passage.text and "Time period" in passage.text
    assert "Source: Labour Force Survey" in passage.text


def test_parent_child_v5_reads_the_title_row_too():
    rows = _rows(_sheet(NISRA, "parent-child-v5"))
    assert any(
        "Time period: Oct to Dec 2023" in c.embedding_text
        and "All persons: 26.9" in c.embedding_text
        for c in rows
    )


def test_v4_keeps_its_saved_title_row_behaviour():
    rows = _rows(_sheet(NISRA, "section-token-v4"))
    assert rows and not any(
        "Time period: Oct to Dec 2023" in c.embedding_text for c in rows
    )


def test_a_first_row_that_is_not_a_title_stays_the_header():
    rows = [
        ["Region", "", "Total"],  # two filled cells: a header, not a title
        ["North", "1", "2"],
    ]
    searched = [c.embedding_text for c in _rows(_sheet(rows, "section-token-v5"))]
    assert any("Region: North" in value and "Total: 2" in value for value in searched)


def test_a_title_without_a_later_header_keeps_the_first_row():
    rows = [
        [TITLE, "", ""],
        ["Note one", "", ""],
        ["Only data", "1", ""],
    ]
    v4 = [c.embedding_text for c in _rows(_sheet(rows, "section-token-v4"))]
    v5 = [c.embedding_text for c in _rows(_sheet(rows, "section-token-v5"))]
    assert v4 == v5
