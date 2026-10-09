"""layout-ocr-v3 merged-column tables and whole cells (spec 0007, slice 1)."""

from __future__ import annotations

import pymupdf
import pytest

from app.ingestion_content.extractors import pdf as extraction
from app.ingestion_content.processing import processing_identity
from app.schemas.ingestion import ExtractNodeV2
from extract_corpus import extract_settings, measure_extract_corpus

LABELS = [
    "All households",
    "Family households",
    "Married-couple",
    "Nonfamily households",
    "Female householder",
    "Male householder",
]
V2_VALUES = [f"{70_000 + i * 1_111:,}" for i in range(len(LABELS))]
V3_VALUES = [f"{80_000 + i * 2_222:,}" for i in range(len(LABELS))]


def _borderless_page() -> pymupdf.Page:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((60, 104), "Characteristic", fontsize=9)
    page.insert_text((306, 104), "2021", fontsize=9)
    page.insert_text((426, 104), "2022", fontsize=9)
    for index, label in enumerate(LABELS):
        y = 128 + index * 20
        page.insert_text((60, y), label + " " + ". " * 12, fontsize=9)
        page.insert_text((306, y), V2_VALUES[index], fontsize=9)
        page.insert_text((426, y), V3_VALUES[index], fontsize=9)
    return pymupdf.open("pdf", document.tobytes())[0]


class _MergedTable:
    """What PyMuPDF returned for the Census appendix: one cell per column."""

    bbox = (54.0, 90.0, 558.0, 250.0)
    rows = []

    def extract(self):
        return [
            ["Characteristic", "2021", "2022"],
            [
                "\n".join(f"{label} . . . . ." for label in LABELS),
                "\n".join(V2_VALUES),
                "\n".join(V3_VALUES),
            ],
        ]


class _Finder:
    tables = [_MergedTable()]


def test_merged_column_detection():
    merged = _MergedTable().extract()
    assert extraction._is_merged_column_table(merged)
    normal = [["Name", "Value"]] + [[f"row {i}", str(i)] for i in range(40)]
    assert not extraction._is_merged_column_table(normal)
    wrapped = [["Topic", "Notes"], ["A", "one\ntwo\nthree\nfour\nfive"], ["B", "short"]]
    assert not extraction._is_merged_column_table(wrapped)


def test_word_rows_keep_each_printed_row_together():
    page = _borderless_page()
    lines = extraction._word_rows(page, (54, 90, 558, 250))
    assert lines[0] == "Characteristic 2021 2022"
    assert f"Married-couple {V2_VALUES[2]} {V3_VALUES[2]}" in lines
    assert all(". ." not in line for line in lines)


@pytest.mark.parametrize("rebuild", [False, True])
def test_layout_page_rebuilds_merged_tables_only_for_v3(monkeypatch, rebuild):
    page = _borderless_page()
    monkeypatch.setattr(type(page), "find_tables", lambda self, *a, **k: _Finder())
    segments, table_count, malformed, _ = extraction._layout_page(
        page,
        page_number=1,
        table_mode="preserve",
        layout_v2=True,
        rebuild_merged_tables=rebuild,
    )
    tables = [s for s in segments if s.block_type == "table"]
    assert table_count == 1
    text = "\n".join(s.text for s in tables)
    married_line = f"Married-couple {V2_VALUES[2]} {V3_VALUES[2]}"
    if rebuild:
        assert married_line in text.splitlines()
        assert tables[0].attributes["table"]["reconstruction"] == "word-rows"
    else:
        assert married_line not in text
    assert malformed == 0


def test_v3_keeps_long_cells_whole_while_v2_cuts_them():
    rows = [
        ["Measure", "Values"],
        ["Median", " ".join(f"{n:,}" for n in range(60_000, 60_300))],
    ]
    v2_groups, v2_cut = extraction._table_row_groups(rows, "markdown", table_id="t")
    v3_groups, v3_cut = extraction._table_row_groups(
        rows, "markdown", table_id="t", cell_limit=None
    )
    assert v2_cut is True
    assert v3_cut is False
    assert "60,299" in "\n".join(g[0] for g in v3_groups)
    assert "60,299" not in "\n".join(g[0] for g in v2_groups)


def test_v3_schema_version_and_identity():
    v3 = ExtractNodeV2(
        id="extract", type="extract", strategy="auto", config_version="layout-ocr-v3"
    )
    assert extraction.extractor_version_for_settings(v3) == (
        extraction.LAYOUT_OCR_V3_EXTRACTOR_VERSION
    )
    with pytest.raises(ValueError, match="requires Auto"):
        ExtractNodeV2(
            id="extract",
            type="extract",
            strategy="native_text",
            config_version="layout-ocr-v3",
        )

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

    assert identity("layout-ocr-v2") != identity("layout-ocr-v3")


def test_v3_matches_v2_on_the_extract_corpus(tmp_path):
    include_ocr = "eng" in extraction.installed_ocr_languages()
    (tmp_path / "v2").mkdir()
    (tmp_path / "v3").mkdir()
    v2 = measure_extract_corpus(
        tmp_path / "v2", config_version="layout-ocr-v2", include_ocr=include_ocr
    )
    v3 = measure_extract_corpus(
        tmp_path / "v3", config_version="layout-ocr-v3", include_ocr=include_ocr
    )
    assert v3 == v2
