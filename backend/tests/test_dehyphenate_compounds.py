"""Compound-aware de-hyphenation (spec 0007, slice 4)."""

from __future__ import annotations

from copy import deepcopy

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import default_structure_steps
from app.schemas.ingestion import CleanNodeV2

TEXT = (
    "Among family households, married-\ncouple families had the highest income.\n"
    "The survey collects infor-\nmation every year from Mc-\nDonald County."
)


def _clean(mode: str):
    steps = deepcopy(default_structure_steps())
    for step in steps:
        if step["type"] == "dehyphenate":
            step["mode"] = mode
    node = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=steps,
    )
    extracted = build_extracted_document(
        [
            CanonicalInputSegment(text=TEXT, page_number=1, block_type="paragraph"),
            CanonicalInputSegment(
                text="| Married-couple | 110,800 |", page_number=2, block_type="table"
            ),
        ],
        media_type="application/pdf",
    )
    return clean_document(
        extracted,
        node,
        cleaner_for_node(node),
        extractor_version="test",
        configuration_hash="d" * 64,
    )


def test_compound_mode_keeps_known_hyphenated_words():
    text = _clean("conservative-compounds").blocks[0].text
    assert "married-couple families" in text
    assert "information every year" in text
    # A capitalised continuation is never joined, as in the conservative mode.
    assert "McDonald" not in text
    assert "marriedcouple" not in text


def test_conservative_mode_is_unchanged():
    text = _clean("conservative").blocks[0].text
    assert "marriedcouple" in text
    assert "information" in text


def test_new_profiles_use_the_compound_mode():
    modes = [s["mode"] for s in default_structure_steps() if s["type"] == "dehyphenate"]
    assert modes == ["conservative-compounds"]
