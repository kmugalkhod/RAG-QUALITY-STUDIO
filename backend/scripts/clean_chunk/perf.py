"""Spec 0012 Part C timings on synthetic input. Free; no database or provider.

    python scripts/clean_chunk/perf.py

Prints seconds for: chunking one 2 MB block (C1), cleaning 1,000 pages with
20,000 blocks (C2), and removing control characters from a 2 MB block (C3), plus
a SHA-256 of each output so a later run can show the output did not change.
"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import _controls, default_structure_steps
from app.schemas.ingestion import CleanNodeV2, SectionTokenChunkNodeV2

SENTENCE = "The archive keeps lanterns, maps and letters from every harbour town. "


def _clean_node():
    return CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=deepcopy(default_structure_steps()),
    )


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def _timed(function):
    started = time.perf_counter()
    result = function()
    return round(time.perf_counter() - started, 3), result


def chunk_two_megabytes(version: str):
    text = (SENTENCE * (2_000_000 // len(SENTENCE) + 1))[:2_000_000]
    extracted = build_extracted_document(
        [CanonicalInputSegment(text=text, page_number=1, block_type="paragraph")],
        media_type="text/plain",
    )
    node = _clean_node()
    cleaned = clean_document(
        extracted,
        node,
        cleaner_for_node(node),
        extractor_version="perf",
        configuration_hash="0" * 64,
    )
    chunk = SectionTokenChunkNodeV2(
        id="chunk", type="chunk", algorithm="section_token", config_version=version
    )
    seconds, result = _timed(lambda: chunk_cleaned_document(cleaned, chunk))
    return seconds, _digest([c.as_record() for c in result.chunks])


def clean_thousand_pages():
    segments = [
        CanonicalInputSegment(
            text=f"Page {page} paragraph {block}. " + SENTENCE,
            page_number=page,
            block_type="paragraph",
        )
        for page in range(1, 1001)
        for block in range(20)
    ]
    extracted = build_extracted_document(segments, media_type="application/pdf")
    node = _clean_node()
    seconds, cleaned = _timed(
        lambda: clean_document(
            extracted,
            node,
            cleaner_for_node(node),
            extractor_version="perf",
            configuration_hash="0" * 64,
        )
    )
    return seconds, _digest([b.text for b in cleaned.blocks])


def remove_controls():
    text = ("Lantern\u0007 maps​ and­ letters.\n" * 60_000)[:2_000_000]
    block = build_extracted_document(
        [CanonicalInputSegment(text=text, page_number=1, block_type="paragraph")],
        media_type="text/plain",
    ).blocks[0]
    seconds, (value, removed) = _timed(lambda: _controls(block))
    return seconds, _digest([value, removed])


def main():
    results = {}
    for version in ("section-token-v1", "section-token-v2"):
        results[f"C1 chunk 2 MB block ({version})"] = chunk_two_megabytes(version)
    results["C2 clean 1,000 pages x 20 blocks"] = clean_thousand_pages()
    results["C3 control characters, 2 MB"] = remove_controls()
    for name, (seconds, digest) in results.items():
        print(f"{name}: {seconds} s  output {digest}")


if __name__ == "__main__":
    main()
