"""Report-only quality findings for native-text-v1 PDFs (Slice 6, decision D2)."""

from __future__ import annotations

import pymupdf

from app.ingestion_content import CanonicalInputSegment, build_extracted_document
from app.ingestion_content.extractors import pdf as extraction
from app.ingestion_content.processing import NativeTextExtractor
from app.ingestion_content.quality import quality_allows_publication
from app.schemas.ingestion import ExtractNodeV2


def _legacy(**updates) -> ExtractNodeV2:
    return ExtractNodeV2.model_validate({"id": "extract", "type": "extract", **updates})


def _blank_middle_page(path):
    with pymupdf.open() as document:
        for text in ("First page has native text.", None, "Third page has text."):
            page = document.new_page(width=612, height=792)
            if text:
                page.insert_text((54, 100), text, fontsize=12)
        document.save(path)


def test_legacy_pdf_reports_blank_pages_without_changing_publication(tmp_path):
    path = tmp_path / "blank-middle.pdf"
    _blank_middle_page(path)

    document, version = extraction.extract_document(
        path, "application/pdf", path.name, _legacy()
    )

    assert version == NativeTextExtractor.version
    assert document.measurements.quality_decision == "pass"
    assert quality_allows_publication("default-v1", "pass")
    empty = next(
        finding for finding in document.findings if finding.code == "empty_pages"
    )
    assert empty.severity == "warning"
    assert empty.page_numbers == [2]
    assert empty.remediation.endswith(extraction.LEGACY_QUALITY_REMEDIATION)
    assert [page.character_count for page in document.pages] == [27, 0, 20]
    assert document.measurements.empty_page_count == 1


def test_legacy_blocks_are_unchanged_by_report_only_findings(tmp_path):
    path = tmp_path / "blank-middle.pdf"
    _blank_middle_page(path)
    document, _ = extraction.extract_document(
        path, "application/pdf", path.name, _legacy()
    )
    previous = build_extracted_document(
        list(NativeTextExtractor().extract(path, "application/pdf")),
        media_type="application/pdf",
        title=path.name,
    )
    assert [block.model_dump() for block in document.blocks] == [
        block.model_dump() for block in previous.blocks
    ]


def test_strict_policy_errors_become_warnings_and_keep_the_decision():
    document = build_extracted_document(
        [CanonicalInputSegment(text="Garbled �� text", page_number=1)],
        media_type="application/pdf",
        page_metadata={
            1: {"origin": "native", "character_count": 16, "block_count": 1}
        },
    )
    reported = extraction._report_only_quality(document, "strict-v1", duration_ms=3)

    codes = {finding.code: finding for finding in reported.findings}
    assert codes["replacement_character_ratio_high"].severity == "warning"
    assert all(finding.severity != "error" for finding in reported.findings)
    assert reported.measurements.quality_decision == "pass"
    assert reported.measurements.extraction_duration_ms == 3


def test_language_policy_still_decides_legacy_publication(tmp_path):
    path = tmp_path / "english.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text(
            (54, 100), "The policy is for the team and the owner.", fontsize=12
        )
        document.save(path)

    document, _ = extraction.extract_document(
        path,
        "application/pdf",
        path.name,
        _legacy(language_policy={"allowlist": ["fr"], "disallowed_action": "exclude"}),
    )
    assert document.measurements.quality_decision == "exclude"
    assert "language_not_allowed" in {finding.code for finding in document.findings}
