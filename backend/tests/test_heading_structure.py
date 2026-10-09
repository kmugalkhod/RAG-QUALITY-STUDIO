"""layout-ocr-v2 PDF headings and Auto structure (Slice 3 of the Extract plan)."""

from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher

import pymupdf

from app.ingestion_content import (
    CanonicalInputSegment,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import default_structure_steps
from app.ingestion_content.extractors import pdf as extraction
from app.schemas.ingestion import CleanNodeV2, SectionTokenChunkNodeV2
from extract_corpus import expectations, extract, extract_settings, save_headings_pdf


def _v2(strategy: str = "auto"):
    return extract_settings(strategy, "layout-ocr-v2")


def _heading(text: str, size: float, page: int = 1) -> CanonicalInputSegment:
    return CanonicalInputSegment(
        text=text,
        page_number=page,
        block_type="heading",
        attributes={"origin": "layout", "font_size": size},
    )


def _body(text: str, page: int = 1) -> CanonicalInputSegment:
    return CanonicalInputSegment(text=text, page_number=page, block_type="paragraph")


def test_heading_structure_assigns_title_levels_and_paths():
    result = extraction._heading_structure(
        [
            _heading("Guide", 24),
            _heading("Setup", 18),
            _body("setup body"),
            _heading("Install", 14),
            _body("install body"),
            _body("next page", page=2),
            _heading("Usage", 18.2, page=2),
            _body("usage body", page=2),
        ]
    )
    assert [(item.block_type, item.heading_path) for item in result] == [
        ("title", ()),
        ("heading", ()),
        ("paragraph", ("Setup",)),
        ("heading", ("Setup",)),
        ("paragraph", ("Setup", "Install")),
        ("paragraph", ("Setup", "Install")),
        ("heading", ()),
        ("paragraph", ("Usage",)),
    ]
    assert [
        item.attributes.get("heading_level") for item in result if item.attributes
    ] == [
        None,
        1,
        2,
        1,
    ]


def test_a_lone_heading_is_a_section_not_a_title():
    result = extraction._heading_structure([_heading("Summary", 16), _body("body")])
    assert [item.block_type for item in result] == ["heading", "paragraph"]
    assert result[1].heading_path == ("Summary",)


def test_bold_coverage_decides_body_size_headings():
    regular = {"text": "The ", "size": 11, "font": "Helvetica", "flags": 0}
    bold = {"text": "critical rule", "size": 11, "font": "Helvetica-Bold", "flags": 16}
    tail = {"text": " applies to every team.", "size": 11, "font": "Helvetica"}

    def kind(text, spans):
        return extraction._classify_block_v2(
            text, spans, body_size=11, top=100, page_height=792
        )[0]

    assert kind("The critical rule applies to every team.", [regular, bold, tail]) == (
        "paragraph"
    )
    assert kind("Scope and owners", [{**bold, "text": "Scope and owners"}]) == "heading"
    assert kind("1.2 Scope.", [{**bold, "text": "1.2 Scope."}]) == "heading"
    assert kind("A bold sentence.", [{**bold, "text": "A bold sentence."}]) == (
        "paragraph"
    )


def test_v2_heading_paths_reach_section_chunks(tmp_path):
    path = tmp_path / "headings.pdf"
    save_headings_pdf(path)
    extracted = extract(path, "application/pdf", _v2())
    clean = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=deepcopy(default_structure_steps()),
    )
    cleaned = clean_document(
        extracted,
        clean,
        cleaner_for_node(clean),
        extractor_version=extraction.LAYOUT_OCR_V2_EXTRACTOR_VERSION,
        configuration_hash="c" * 64,
    )
    chunks = chunk_cleaned_document(
        cleaned,
        SectionTokenChunkNodeV2.model_validate(
            {
                "id": "chunk",
                "type": "chunk",
                "algorithm": "section_token",
                "target_tokens": 600,
                "maximum_tokens": 800,
                "overlap_tokens": 80,
            }
        ),
    ).chunks
    spec = expectations()
    for marker, heading_path in spec["heading_paths"].items():
        chunk = next(chunk for chunk in chunks if marker in chunk.text)
        assert chunk.embedding_text.startswith(f"Section: {' > '.join(heading_path)}")
    # Each heading followed by body text shares its chunk; only the title, which is
    # followed directly by a heading, stands alone (as a Markdown "# Title" does).
    alone = [chunk.text for chunk in chunks if chunk.text.strip() in spec["headings"]]
    assert alone == []


def test_v2_auto_keeps_native_text_when_layout_loses_it(tmp_path, monkeypatch):
    path = tmp_path / "native.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text(
            (54, 100), "Native text that layout analysis drops.", fontsize=12
        )
        document.save(path)

    def losing_layout(page, *, page_number, table_mode, **_):
        segment = CanonicalInputSegment(
            text="Native", page_number=page_number, block_type="paragraph"
        )
        return [segment], 0, 0, False

    monkeypatch.setattr(extraction, "_layout_page", losing_layout)
    document = extract(path, "application/pdf", _v2())
    assert document.pages[0].origin == "native"
    assert document.pages[0].fallback_reason == "layout_text_loss"
    assert "layout analysis drops" in document.blocks[0].text


def test_v2_auto_preserves_native_text_on_a_simple_page(tmp_path):
    expected = (
        "Robust ingestion A native paragraph with enough text for extraction. "
        "A second line keeps the page ordinary."
    )
    path = tmp_path / "simple.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((54, 54), "Robust ingestion", fontsize=22)
        page.insert_text(
            (54, 100),
            "A native paragraph with enough text for extraction.",
            fontsize=12,
        )
        page.insert_text(
            (54, 116), "A second line keeps the page ordinary.", fontsize=12
        )
        document.save(path)

    document = extract(path, "application/pdf", _v2())
    observed = " ".join(" ".join(block.text.split()) for block in document.blocks)
    assert document.pages[0].origin == "layout"
    assert document.pages[0].fallback_reason == "layout_structure"
    assert SequenceMatcher(None, expected, observed).ratio() >= 0.995
