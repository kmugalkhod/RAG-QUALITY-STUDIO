"""Extract-quality corpus baseline (Slice 0 of docs/extract-node-improvement-plan.md).

`layout-ocr-v1` is frozen: its measured values and exact output stay as recorded here
so saved pipeline versions reproduce. Improved behavior is measured under later
configuration versions in their own tests.
"""

from __future__ import annotations

import json
import os

from app.ingestion_content.extractors import pdf as extraction
from extract_corpus import (
    GOLDEN_PATH,
    measure_extract_corpus,
    output_digests,
)


# Measured 2026-10-06 in the pinned backend container; see
# docs/ingestion-corpus-baseline.md "Before Extract v2".
V1_BASELINE: dict[str, float | int | str] = {
    # F1: right-column paragraphs interleave with the left column.
    "auto_reading_order_percent": 80.0,
    "layout_aware_reading_order_percent": 80.0,
    # F10: Auto keeps single-column pages as one native block, losing all headings.
    "auto_heading_precision_percent": 0.0,
    "auto_heading_recall_percent": 0.0,
    "auto_title_blocks": 0,
    "auto_heading_path_coverage_percent": 0.0,
    # F3/F4: a bold-term paragraph becomes a heading, page 3 gets a second title
    # and no body block carries a heading path.
    "layout_aware_heading_precision_percent": 83.333,
    "layout_aware_heading_recall_percent": 100.0,
    "layout_aware_title_blocks": 2,
    "layout_aware_heading_path_coverage_percent": 0.0,
    # F2: the 40-row table is truncated and fails the Balanced policy.
    "auto_large_table_cell_retention_percent": 40.65,
    "auto_large_table_malformed_count": 1,
    "auto_large_table_decision": "fail",
    "layout_aware_large_table_cell_retention_percent": 40.65,
    "layout_aware_large_table_malformed_count": 1,
    "layout_aware_large_table_decision": "fail",
    # F8: DOCX data rows are separate blocks without the header row.
    "docx_header_coverage_percent": 0.0,
    # F5: one OCR block per line instead of one per paragraph.
    "ocr_blocks_for_paragraph": 4,
}


def test_layout_ocr_v1_output_matches_recorded_golden(tmp_path):
    observed = output_digests(tmp_path)
    if os.environ.get("UPDATE_EXTRACT_GOLDEN") == "1":
        GOLDEN_PATH.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
    expected = json.loads(GOLDEN_PATH.read_text())
    assert observed == expected


def test_layout_ocr_v1_extract_quality_baseline(tmp_path):
    include_ocr = "eng" in extraction.installed_ocr_languages()
    report = measure_extract_corpus(tmp_path, include_ocr=include_ocr)
    expected = dict(V1_BASELINE)
    if not include_ocr:
        expected.pop("ocr_blocks_for_paragraph", None)
    assert report == expected


def test_layout_ocr_v2_extract_quality(tmp_path):
    """Measures v2 changes so far; every measure not listed matches v1."""

    include_ocr = "eng" in extraction.installed_ocr_languages()
    report = measure_extract_corpus(
        tmp_path, config_version="layout-ocr-v2", include_ocr=include_ocr
    )
    expected = {
        **V1_BASELINE,
        # Slice 1: computed column order is kept.
        "auto_reading_order_percent": 100.0,
        "layout_aware_reading_order_percent": 100.0,
        # Slice 2: whole tables in header-repeating row groups.
        "auto_large_table_cell_retention_percent": 100.0,
        "auto_large_table_malformed_count": 0,
        "auto_large_table_decision": "pass",
        "layout_aware_large_table_cell_retention_percent": 100.0,
        "layout_aware_large_table_malformed_count": 0,
        "layout_aware_large_table_decision": "pass",
        # Slice 3: headings, one title and heading paths under Auto and Layout-aware.
        "auto_heading_precision_percent": 100.0,
        "auto_heading_recall_percent": 100.0,
        "auto_title_blocks": 1,
        "auto_heading_path_coverage_percent": 100.0,
        "layout_aware_heading_precision_percent": 100.0,
        "layout_aware_heading_recall_percent": 100.0,
        "layout_aware_title_blocks": 1,
        "layout_aware_heading_path_coverage_percent": 100.0,
    }
    if not include_ocr:
        expected.pop("ocr_blocks_for_paragraph", None)
    assert report == expected
