"""layout-ocr-v4 (spec 0008, B3): words broken at a soft hyphen are rejoined.

Census P60-279 marks its line-break hyphens as U+00AD. Cleaning removes the control
character and then reflows the line break into a space, so v3 text becomes
"house holds". PyMuPDF's base-14 fonts draw U+00AD as a plain hyphen, so the tests
put the soft hyphen back into the layout result, as the real file's text layer has it.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from app.ingestion_content import (
    CanonicalInputSegment,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import default_structure_steps
from app.ingestion_content.extractors import extract_document
from app.ingestion_content.extractors import pdf as extraction
from app.schemas.ingestion import CleanNodeV2
from extract_corpus import extract_settings

LINES = [
    "Among family house-",
    "holds, married couples had the highest median income of",
    "all family types, and the survey thanks every respondent for",
    "their dedi-",
    "cation. Real income changed by 2.9 per-cent from 2021.",
]


@pytest.fixture
def soft_hyphen_pdf(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "soft.pdf"
    document = pymupdf.open()
    page = document.new_page()
    for index, line in enumerate(LINES):
        page.insert_text((72, 72 + index * 14), line, fontsize=11)
    document.save(path)

    original = extraction._layout_page

    def with_soft_hyphens(*args, **kwargs):
        segments, *rest = original(*args, **kwargs)
        softened = [
            replace(item, text=item.text.replace("-\n", "­\n").replace("per-", "per­"))
            for item in segments
        ]
        softened.append(
            CanonicalInputSegment(
                text="| Number (thou­\nsands) | Median |",
                page_number=1,
                block_type="table",
            )
        )
        return (softened, *rest)

    monkeypatch.setattr(extraction, "_layout_page", with_soft_hyphens)
    return path


def _extract(path: Path, version: str):
    document, _ = extract_document(
        path, "application/pdf", "soft", extract_settings(config_version=version)
    )
    return document


def _clean(document):
    node = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=deepcopy(default_structure_steps()),
    )
    return clean_document(
        document,
        node,
        cleaner_for_node(node),
        extractor_version="test",
        configuration_hash="d" * 64,
    )


def _paragraphs(document) -> str:
    return "\n".join(b.text for b in document.blocks if b.type != "table")


def test_v4_rejoins_words_broken_at_a_soft_hyphen(soft_hyphen_pdf):
    document = _extract(soft_hyphen_pdf, "layout-ocr-v4")
    text = _paragraphs(document)
    assert "Among family households, married" in text.replace("\n", " ")
    assert "their dedication." in text.replace("\n", " ")
    # A soft hyphen inside a line is left for cleaning, which removes it.
    assert "per­cent" in text
    assert "­\n" not in text
    page = document.pages[0]
    assert page.character_count == sum(len(b.text) for b in document.blocks)


def test_v4_leaves_table_cells_as_extracted(soft_hyphen_pdf):
    document = _extract(soft_hyphen_pdf, "layout-ocr-v4")
    tables = [b.text for b in document.blocks if b.type == "table"]
    assert tables == ["| Number (thou­\nsands) | Median |"]


def test_v3_output_is_unchanged(soft_hyphen_pdf):
    text = _paragraphs(_extract(soft_hyphen_pdf, "layout-ocr-v3"))
    assert "house­\nholds" in text
    assert "dedi­\ncation" in text


def test_default_cleaning_keeps_rejoined_words_whole(soft_hyphen_pdf):
    v3 = _paragraphs(_clean(_extract(soft_hyphen_pdf, "layout-ocr-v3")))
    v4 = _paragraphs(_clean(_extract(soft_hyphen_pdf, "layout-ocr-v4")))
    # The v3 defect this fixes: the word is split in two after cleaning.
    assert "house holds" in v3 and "dedi cation" in v3
    assert "households, married" in v4 and "dedication." in v4
    assert "percent" in v4
    assert "house holds" not in v4
