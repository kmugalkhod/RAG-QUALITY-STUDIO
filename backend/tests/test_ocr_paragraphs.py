"""layout-ocr-v2 OCR paragraphs and OCR language lookup (Slice 4 of the Extract plan)."""

from __future__ import annotations

import subprocess
import pymupdf
import pytest

from app.ingestion_content.extractors import pdf as extraction
from extract_corpus import (
    expectations,
    extract,
    extract_settings,
    save_ocr_paragraph_pdf,
)


def _row(block, paragraph, line, word, left, top, text, conf="90"):
    return {
        "block_num": str(block),
        "par_num": str(paragraph),
        "line_num": str(line),
        "word_num": str(word),
        "left": str(left),
        "top": str(top),
        "width": "50",
        "height": "20",
        "conf": conf,
        "text": text,
    }


def test_ocr_rows_become_one_block_per_paragraph_in_engine_order():
    rows = [
        # Tesseract reports the left column (block 1) before the right (block 2),
        # even though the right column's first line is higher on the page.
        _row(1, 1, 1, 1, 10, 100, "Left", "80"),
        _row(1, 1, 1, 2, 70, 100, "first", "90"),
        _row(1, 1, 2, 1, 10, 130, "second", "100"),
        _row(2, 1, 1, 1, 400, 40, "Right", "70"),
    ]
    segments = extraction._ocr_paragraphs(
        rows,
        image_width=1000,
        image_height=1000,
        page_number=3,
        attributes={"origin": "ocr", "engine": "tesseract"},
    )

    assert [segment.text for segment in segments] == ["Left first\nsecond", "Right"]
    left = segments[0]
    assert left.page_number == 3
    assert left.block_type == "paragraph"
    assert left.attributes["origin"] == "ocr"
    assert left.attributes["line_count"] == 2
    assert left.attributes["engine_confidence"] == 90.0
    assert left.attributes["line_boxes"] == [
        [0.01, 0.1, 0.12, 0.12],
        [0.01, 0.13, 0.06, 0.15],
    ]
    assert (left.bounding_box.left, left.bounding_box.top) == (0.01, 0.1)
    assert left.bounding_box.bottom == pytest.approx(0.15)


def test_v2_scan_keeps_a_paragraph_together(tmp_path):
    if "eng" not in extraction.installed_ocr_languages():
        pytest.skip("The deterministic container OCR engine is not installed.")
    path = tmp_path / "ocr-paragraph.pdf"
    save_ocr_paragraph_pdf(path)
    ocr = {
        "mode": "always",
        "languages": ["eng"],
        "rotate_pages": False,
        "deskew": False,
    }

    v1 = extract(path, "application/pdf", extract_settings("auto", ocr=ocr))
    v2 = extract(
        path, "application/pdf", extract_settings("auto", "layout-ocr-v2", ocr=ocr)
    )

    assert len(v1.blocks) == 4
    assert len(v2.blocks) == 1
    assert v2.blocks[0].attributes["line_count"] == 4
    expected = expectations()["ocr_paragraph"].lower().split()
    assert v2.blocks[0].text.lower().split() == expected
    assert v2.pages[0].ocr_confidence == v1.pages[0].ocr_confidence


def test_ocr_off_never_lists_language_packs(tmp_path, monkeypatch):
    path = tmp_path / "native.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((54, 100), "A native paragraph with enough text.", fontsize=12)
        document.save(path)

    def unexpected():
        raise AssertionError("OCR languages were listed with OCR off.")

    monkeypatch.setattr(extraction, "installed_ocr_languages", unexpected)
    for version in ("layout-ocr-v1", "layout-ocr-v2"):
        document = extract(path, "application/pdf", extract_settings("auto", version))
        assert "native paragraph" in " ".join(block.text for block in document.blocks)


def test_language_packs_are_listed_once_per_cache_window(monkeypatch):
    calls = []

    def fake_tesseract(args, *, timeout, stdout=subprocess.DEVNULL):
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, "List of available languages (3):\neng\nosd\nfra\n", ""
        )

    clock = [1_000.0]
    monkeypatch.setattr(extraction, "_ocr_language_cache", None)
    monkeypatch.setattr(extraction, "_run_tesseract", fake_tesseract)
    monkeypatch.setattr(extraction.time, "monotonic", lambda: clock[0])

    assert extraction.installed_ocr_languages() == ["eng", "fra"]
    clock[0] += extraction.OCR_LANGUAGE_CACHE_SECONDS - 1
    assert extraction.installed_ocr_languages() == ["eng", "fra"]
    assert len(calls) == 1
    clock[0] += 2
    assert extraction.installed_ocr_languages() == ["eng", "fra"]
    assert len(calls) == 2


def test_returned_language_lists_cannot_change_the_cache(monkeypatch):
    monkeypatch.setattr(extraction, "_ocr_language_cache", None)
    monkeypatch.setattr(extraction, "_list_ocr_languages", lambda: ["eng"])
    extraction.installed_ocr_languages().append("deu")
    assert extraction.installed_ocr_languages() == ["eng"]
