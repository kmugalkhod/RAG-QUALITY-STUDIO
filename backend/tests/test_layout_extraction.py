from __future__ import annotations

from pathlib import Path
import subprocess
from difflib import SequenceMatcher
from io import BytesIO
import json
import re

import pymupdf
import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.ingestion_content.extractors import pdf as extraction
from app.ingestion_content.processing import IngestionStageError
from app.ingestion_content.quality import evaluate_quality, measured_document
from app.schemas.ingestion import ExtractNodeV2


CORPUS_MANIFEST = (
    Path(__file__).parent / "fixtures" / "ingestion_corpus" / "manifest.json"
)


def save_native_pdf(path: Path, *, table: bool = False, two_columns: bool = False):
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((54, 54), "Robust ingestion", fontsize=22)
        if two_columns:
            page.insert_textbox(
                pymupdf.Rect(54, 90, 280, 340),
                "Left column first.\nLeft column second.",
                fontsize=12,
            )
            page.insert_textbox(
                pymupdf.Rect(332, 90, 558, 340),
                "Right column first.\nRight column second.",
                fontsize=12,
            )
        else:
            page.insert_text(
                (54, 100),
                "A native paragraph with enough text for extraction.",
                fontsize=12,
            )
        if table:
            x_values = [54, 204, 354]
            y_values = [400, 430, 460]
            for x in x_values:
                page.draw_line((x, y_values[0]), (x, y_values[-1]))
            for y in y_values:
                page.draw_line((x_values[0], y), (x_values[-1], y))
            page.insert_text((62, 420), "Header A", fontsize=10)
            page.insert_text((212, 420), "Header B", fontsize=10)
            page.insert_text((62, 450), "Cell A", fontsize=10)
            page.insert_text((212, 450), "Cell B", fontsize=10)
        document.save(path)


def save_scanned_pdf(path: Path, text: str = "Scanned policy text"):
    with pymupdf.open() as native:
        page = native.new_page(width=612, height=792)
        page.insert_textbox(pymupdf.Rect(72, 110, 540, 220), text, fontsize=24, align=0)
        image = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
        with pymupdf.open() as scanned:
            target = scanned.new_page(width=612, height=792)
            target.insert_image(target.rect, stream=image.tobytes("png"))
            scanned.save(path)


def save_mixed_pdf(path: Path):
    native_path = path.with_name("native-source.pdf")
    scan_path = path.with_name("scan-source.pdf")
    save_native_pdf(native_path)
    save_scanned_pdf(scan_path)
    with pymupdf.open() as output:
        with pymupdf.open(native_path) as native:
            output.insert_pdf(native)
        with pymupdf.open(scan_path) as scan:
            output.insert_pdf(scan)
        output.save(path)


def save_rotated_scan(path: Path, text: str):
    repeated = " ".join([text] * 8)
    with pymupdf.open() as native:
        page = native.new_page(width=612, height=792)
        y = 80
        for start in range(0, len(repeated), 48):
            page.insert_text((50, y), repeated[start : start + 48], fontsize=16)
            y += 26
        pixmap = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
    image = Image.open(BytesIO(pixmap.tobytes("png"))).rotate(
        90, expand=True, fillcolor=255
    )
    image_bytes = BytesIO()
    image.save(image_bytes, format="PNG")
    with pymupdf.open() as rotated:
        page = rotated.new_page(width=612, height=792)
        page.insert_image(page.rect, stream=image_bytes.getvalue())
        rotated.save(path)


def settings(**updates):
    value = {
        "id": "extract",
        "type": "extract",
        "strategy": "auto",
        "ocr": {"mode": "off", "languages": ["eng"]},
        "tables": "preserve",
        "quality_policy": "default-v1",
        "config_version": "layout-ocr-v1",
    }
    value.update(updates)
    return ExtractNodeV2.model_validate(value)


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def character_error_rate(expected: str, observed: str) -> float:
    previous = list(range(len(observed) + 1))
    for expected_character in expected:
        current = [previous[0] + 1]
        for index, observed_character in enumerate(observed, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index] + 1,
                    previous[index - 1] + int(expected_character != observed_character),
                )
            )
        previous = current
    return previous[-1] / max(1, len(expected))


def measure_reviewed_corpus(tmp_path: Path) -> dict[str, float | int]:
    manifest = json.loads(CORPUS_MANIFEST.read_text())
    native_path = tmp_path / "corpus-native.pdf"
    scan_path = tmp_path / "corpus-scan.pdf"
    mixed_path = tmp_path / "corpus-mixed.pdf"
    rotated_path = tmp_path / "corpus-rotated.pdf"
    layout_path = tmp_path / "corpus-layout.pdf"
    save_native_pdf(native_path)
    save_scanned_pdf(scan_path, manifest["ocr_text"])
    save_mixed_pdf(mixed_path)
    save_rotated_scan(rotated_path, manifest["rotated_ocr_text"])
    save_native_pdf(layout_path, table=True, two_columns=True)

    native, _ = extraction.extract_document(
        native_path,
        "application/pdf",
        native_path.name,
        settings(strategy="native"),
    )
    native_observed = normalized(" ".join(block.text for block in native.blocks))
    native_expected = normalized(manifest["native_text"])
    native_ratio = SequenceMatcher(None, native_expected, native_observed).ratio()

    ocr_settings = settings(
        ocr={
            "mode": "always",
            "languages": ["eng"],
            "rotate_pages": False,
            "deskew": True,
            "dpi": 200,
        }
    )
    scan, _ = extraction.extract_document(
        scan_path, "application/pdf", scan_path.name, ocr_settings
    )
    scan_text = normalized(" ".join(block.text for block in scan.blocks))
    rotated, _ = extraction.extract_document(
        rotated_path,
        "application/pdf",
        rotated_path.name,
        settings(
            ocr={
                "mode": "always",
                "languages": ["eng"],
                "rotate_pages": True,
                "deskew": True,
                "dpi": 200,
            }
        ),
    )
    rotated_text = normalized(" ".join(block.text for block in rotated.blocks))
    rotated_expected = normalized(" ".join([manifest["rotated_ocr_text"]] * 8))
    ocr_rates = sorted(
        [
            character_error_rate(manifest["ocr_text"].lower(), scan_text.lower()),
            character_error_rate(rotated_expected.lower(), rotated_text.lower()),
        ]
    )

    mixed, _ = extraction.extract_document(
        mixed_path,
        "application/pdf",
        mixed_path.name,
        settings(ocr={"mode": "auto", "languages": ["eng"], "deskew": False}),
    )
    layout, _ = extraction.extract_document(
        layout_path,
        "application/pdf",
        layout_path.name,
        settings(strategy="layout_aware"),
    )
    layout_text = "\n".join(block.text for block in layout.blocks)
    order_positions = [layout_text.index(value) for value in manifest["reading_order"]]
    order_pairs = [
        order_positions[left] < order_positions[right]
        for left in range(len(order_positions))
        for right in range(left + 1, len(order_positions))
    ]
    table = next(block for block in layout.blocks if block.type == "table")
    observed_cells = {cell for row in table.attributes["table"]["rows"] for cell in row}
    matching_cells = sum(cell in observed_cells for cell in manifest["table_cells"])
    rerun, _ = extraction.extract_document(
        layout_path,
        "application/pdf",
        layout_path.name,
        settings(strategy="layout_aware"),
    )
    deterministic = layout.model_dump(
        exclude={"measurements": {"extraction_duration_ms"}}
    ) == rerun.model_dump(exclude={"measurements": {"extraction_duration_ms"}})
    return {
        "native_text_preservation_percent": round(native_ratio * 100, 3),
        "ocr_cer_median_percent": round(sum(ocr_rates) / len(ocr_rates) * 100, 3),
        "ocr_cer_p95_percent": round(ocr_rates[-1] * 100, 3),
        "reading_order_percent": round(sum(order_pairs) / len(order_pairs) * 100, 3),
        "table_cell_association_percent": round(
            matching_cells / len(manifest["table_cells"]) * 100, 3
        ),
        "deterministic_rerun_percent": 100 if deterministic else 0,
        "mixed_native_pages": mixed.measurements.native_page_count,
        "mixed_ocr_pages": mixed.measurements.ocr_page_count,
        "rotated_correction_degrees": rotated.pages[0].rotation_degrees,
        "native_extraction_ms": native.measurements.extraction_duration_ms,
        "scan_extraction_ms": scan.measurements.extraction_duration_ms,
        "rotated_extraction_ms": rotated.measurements.extraction_duration_ms,
        "layout_extraction_ms": layout.measurements.extraction_duration_ms,
    }


def fake_tesseract(args, *, timeout, stdout=subprocess.DEVNULL):
    if "--list-langs" in args:
        return subprocess.CompletedProcess(
            args, 0, "List of available languages (1):\neng\n", ""
        )
    if "--psm" in args and args[args.index("--psm") + 1] == "0":
        return subprocess.CompletedProcess(args, 0, "Rotate: 0\n", "")
    output_base = Path(args[2])
    output_base.with_suffix(".tsv").write_text(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t20\t30\t120\t25\t94.5\tScanned\n"
        "5\t1\t1\t1\t1\t2\t150\t30\t100\t25\t91.0\tpolicy\n"
        "5\t1\t1\t1\t1\t3\t260\t30\t80\t25\t89.0\ttext\n"
    )
    return subprocess.CompletedProcess(args, 0, "", "")


def test_extract_schema_preserves_legacy_and_rejects_mixed_versions():
    legacy = ExtractNodeV2(id="extract", type="extract")
    assert legacy.strategy == "native_text"
    assert legacy.config_version == "native-text-v1"
    with pytest.raises(ValueError, match="Legacy"):
        ExtractNodeV2(
            id="extract",
            type="extract",
            strategy="auto",
            config_version="native-text-v1",
        )
    with pytest.raises(ValueError, match="requires Auto"):
        ExtractNodeV2(
            id="extract",
            type="extract",
            strategy="native_text",
            config_version="layout-ocr-v1",
        )


def test_layout_profile_preserves_geometry_reading_order_and_table(tmp_path):
    path = tmp_path / "layout.pdf"
    save_native_pdf(path, table=True, two_columns=True)
    document, version = extraction.extract_document(
        path,
        "application/pdf",
        "layout.pdf",
        settings(strategy="layout_aware"),
    )
    assert "pymupdf" in version
    assert document.pages[0].origin == "layout"
    assert document.pages[0].fallback_reason == "layout_profile"
    assert all(block.bounding_box is not None for block in document.blocks)
    assert any(block.type == "title" for block in document.blocks)
    table = next(block for block in document.blocks if block.type == "table")
    assert table.attributes["table"]["rows"][0] == ["Header A", "Header B"]
    assert "| Header A | Header B |" in table.text
    texts = [block.text for block in document.blocks]
    assert texts.index("Left column first.\nLeft column second.") < texts.index(
        "Right column first.\nRight column second."
    )
    assert document.measurements.table_count == 1
    assert document.measurements.quality_decision in {"pass", "warn"}


def test_auto_mixed_pdf_records_exact_native_and_ocr_origins(tmp_path, monkeypatch):
    path = tmp_path / "mixed.pdf"
    save_mixed_pdf(path)
    monkeypatch.setattr(extraction, "installed_ocr_languages", lambda: ["eng"])
    monkeypatch.setattr(extraction, "_run_tesseract", fake_tesseract)
    document, _ = extraction.extract_document(
        path,
        "application/pdf",
        "mixed.pdf",
        settings(ocr={"mode": "auto", "languages": ["eng"], "deskew": False}),
    )
    assert [page.origin for page in document.pages] == ["native", "ocr"]
    assert document.pages[1].fallback_reason == "native_text_below_20_characters"
    assert document.pages[1].ocr_confidence == 91.0
    assert document.measurements.native_page_count == 1
    assert document.measurements.ocr_page_count == 1
    assert document.measurements.ocr_confidence_p05 == 91.0
    assert any(block.attributes.get("origin") == "ocr" for block in document.blocks)
    assert document.measurements.quality_decision == "pass"


def test_ocr_off_and_missing_language_fail_safely(tmp_path, monkeypatch):
    path = tmp_path / "scan.pdf"
    save_scanned_pdf(path)
    document, _ = extraction.extract_document(
        path,
        "application/pdf",
        "scan.pdf",
        settings(),
    )
    assert document.pages[0].origin == "native"
    assert document.measurements.quality_decision == "exclude"
    assert {finding.code for finding in document.findings} >= {
        "ocr_required",
        "no_extractable_text",
    }

    monkeypatch.setattr(extraction, "installed_ocr_languages", lambda: ["eng"])
    with pytest.raises(IngestionStageError, match="language packs"):
        extraction.extract_document(
            path,
            "application/pdf",
            "scan.pdf",
            settings(ocr={"mode": "always", "languages": ["deu"]}),
        )


def test_media_bytes_thumbnail_and_deterministic_output(tmp_path):
    pdf_path = tmp_path / "native.pdf"
    save_native_pdf(pdf_path)
    first, _ = extraction.extract_document(
        pdf_path, "application/pdf", "native.pdf", settings(strategy="native")
    )
    second, _ = extraction.extract_document(
        pdf_path, "application/pdf", "native.pdf", settings(strategy="native")
    )
    assert first.model_dump(
        exclude={"measurements": {"extraction_duration_ms"}}
    ) == second.model_dump(exclude={"measurements": {"extraction_duration_ms"}})
    thumbnail = extraction.render_pdf_thumbnail(pdf_path, 1)
    assert thumbnail.startswith(b"\x89PNG\r\n\x1a\n")

    spoofed = tmp_path / "spoofed.txt"
    spoofed.write_bytes(pdf_path.read_bytes())
    with pytest.raises(IngestionStageError, match="stored media type"):
        extraction.extract_document(
            spoofed, "text/plain", "spoofed.txt", settings(strategy="native")
        )


def test_quality_policy_warns_or_rejects_same_measurements(tmp_path):
    path = tmp_path / "scan.pdf"
    save_scanned_pdf(path)
    document, _ = extraction.extract_document(
        path, "application/pdf", "scan.pdf", settings(quality_policy="warn-v1")
    )
    assert document.measurements.quality_decision == "exclude"

    native_path = tmp_path / "native.pdf"
    save_native_pdf(native_path)
    native, _ = extraction.extract_document(
        native_path, "application/pdf", "native.pdf", settings(strategy="native")
    )
    measured = measured_document(
        native.model_copy(update={"findings": []}),
        duration_ms=1,
        suspicious_reading_order_count=1,
    )
    assert evaluate_quality(measured, "warn-v1").measurements.quality_decision == "warn"
    assert (
        evaluate_quality(measured, "strict-v1").measurements.quality_decision == "fail"
    )


def test_packaged_ocr_extracts_reviewed_scan(tmp_path):
    """Exercise the real packaged OCR engine; local hosts without it skip cleanly."""

    if "eng" not in extraction.installed_ocr_languages():
        pytest.skip("The deterministic container OCR engine is not installed.")
    expected = "Reviewed scanned policy text for robust ingestion"
    path = tmp_path / "reviewed-scan.pdf"
    save_scanned_pdf(path, expected)
    document, version = extraction.extract_document(
        path,
        "application/pdf",
        path.name,
        settings(
            ocr={
                "mode": "always",
                "languages": ["eng"],
                "rotate_pages": False,
                "deskew": False,
                "dpi": 200,
            }
        ),
    )
    observed = " ".join(block.text for block in document.blocks)
    similarity = SequenceMatcher(None, expected.lower(), observed.lower()).ratio()
    assert similarity >= 0.95
    assert document.pages[0].origin == "ocr"
    assert document.pages[0].ocr_confidence is not None
    assert document.measurements.quality_decision in {"pass", "warn"}
    assert "tesseract-cli-v2" in version


def test_reviewed_extraction_corpus_meets_phase_two_thresholds(tmp_path):
    if "eng" not in extraction.installed_ocr_languages():
        pytest.skip("The deterministic container OCR engine is not installed.")
    report = measure_reviewed_corpus(tmp_path)
    assert report["native_text_preservation_percent"] >= 99.5
    assert report["ocr_cer_median_percent"] <= 5
    assert report["ocr_cer_p95_percent"] <= 12
    assert report["reading_order_percent"] >= 95
    assert report["table_cell_association_percent"] >= 95
    assert report["deterministic_rerun_percent"] == 100
    assert report["mixed_native_pages"] == 1
    assert report["mixed_ocr_pages"] == 1
    assert report["rotated_correction_degrees"] == 90


def test_encrypted_malformed_cancelled_and_ocr_limits_fail_safely(
    tmp_path, monkeypatch
):
    native_path = tmp_path / "native.pdf"
    save_native_pdf(native_path)
    encrypted_path = tmp_path / "encrypted.pdf"
    reader = PdfReader(native_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("review-password")
    with encrypted_path.open("wb") as output:
        writer.write(output)
    with pytest.raises(IngestionStageError) as encrypted:
        extraction.extract_document(
            encrypted_path,
            "application/pdf",
            encrypted_path.name,
            settings(strategy="native"),
        )
    assert encrypted.value.code == "encrypted_pdf"

    malformed_path = tmp_path / "malformed.pdf"
    malformed_path.write_bytes(b"%PDF-1.7\nnot-a-valid-pdf")
    with pytest.raises(IngestionStageError) as malformed:
        extraction.extract_document(
            malformed_path,
            "application/pdf",
            malformed_path.name,
            settings(strategy="native"),
        )
    assert malformed.value.code == "malformed_pdf"

    with pytest.raises(IngestionStageError) as cancelled:
        extraction.extract_document(
            native_path,
            "application/pdf",
            native_path.name,
            settings(strategy="native"),
            cancelled=lambda: True,
        )
    assert cancelled.value.code == "cancelled"

    scan_path = tmp_path / "scan.pdf"
    save_scanned_pdf(scan_path)
    monkeypatch.setattr(extraction, "installed_ocr_languages", lambda: ["eng"])
    monkeypatch.setattr(extraction, "MAX_OCR_PIXELS_PER_PAGE", 1)
    with pytest.raises(IngestionStageError) as pixel_limit:
        extraction.extract_document(
            scan_path,
            "application/pdf",
            scan_path.name,
            settings(ocr={"mode": "always", "languages": ["eng"]}),
        )
    assert pixel_limit.value.code == "ocr_pixel_limit"


def test_table_payload_is_bounded():
    rows = [[f"cell-{row}-{column}" * 40 for column in range(20)] for row in range(40)]
    evidence, attributes, truncated = extraction._safe_table(rows, "preserve")
    assert truncated is True
    assert len(attributes["table"]["rows"]) <= 25
    assert all(len(row) <= 10 for row in attributes["table"]["rows"])
    assert len(evidence.encode()) < 16_000
