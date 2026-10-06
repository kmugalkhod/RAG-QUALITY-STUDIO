"""Synthetic Extract-quality corpus and its measurements.

The fixtures are generated deterministically from the reviewed expectations in
`fixtures/ingestion_corpus/manifest.json` (`extract_quality`). They target the
Extract node findings in `docs/extract-node-improvement-plan.md`: multi-block
reading order, PDF headings, large tables, OCR paragraphs and DOCX tables.
"""

from __future__ import annotations

import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf

from app.ingestion_content.contracts import ExtractedDocumentV1
from app.ingestion_content.extractors import pdf as extraction
from app.ingestion_content.extractors.formats import DOCX
from app.schemas.ingestion import ExtractNodeV2


CORPUS_MANIFEST = (
    Path(__file__).parent / "fixtures" / "ingestion_corpus" / "manifest.json"
)
GOLDEN_PATH = (
    Path(__file__).parent / "fixtures" / "ingestion_corpus" / "extract_v1_golden.json"
)
FILLER = (
    "Teams record each review step with its owner, date and outcome so later "
    "readers can follow the decision without asking for missing context."
)


def expectations() -> dict:
    return json.loads(CORPUS_MANIFEST.read_text())["extract_quality"]


def extract_settings(
    strategy: str = "auto", config_version: str = "layout-ocr-v1", **updates
) -> ExtractNodeV2:
    value = {
        "id": "extract",
        "type": "extract",
        "strategy": strategy,
        "ocr": {"mode": "off", "languages": ["eng"]},
        "tables": "preserve",
        "quality_policy": "default-v1",
        "config_version": config_version,
    }
    value.update(updates)
    return ExtractNodeV2.model_validate(value)


def save_two_column_pdf(path: Path) -> None:
    """Three paragraphs per column, the right column offset so blocks stay separate."""

    order = expectations()["two_column_order"]
    left, right = order[:3], order[3:]
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        for index in range(3):
            top = 80 + index * 210
            page.insert_textbox(
                pymupdf.Rect(54, top, 280, top + 190),
                f"{left[index]} paragraph. {FILLER}",
                fontsize=10,
            )
            page.insert_textbox(
                pymupdf.Rect(332, top + 15, 558, top + 205),
                f"{right[index]} paragraph. {FILLER}",
                fontsize=10,
            )
        document.save(path)


def _body(page: pymupdf.Page, top: float, marker: str) -> float:
    rect = pymupdf.Rect(54, top, 558, top + 80)
    page.insert_textbox(rect, f"{marker}. {FILLER}", fontsize=11, fontname="helv")
    return top + 70


def _heading(page: pymupdf.Page, top: float, text: str, size: float) -> float:
    page.insert_text((54, top + size), text, fontsize=size, fontname="hebo")
    return top + size + 18


def _bold_term_paragraph(page: pymupdf.Page, top: float) -> float:
    """A body paragraph whose first line contains one bold term."""

    baseline = top + 11
    x = 54.0
    for text, font in (
        ("The ", "helv"),
        ("critical rule", "hebo"),
        (" applies to every team that publishes reviewed documents.", "helv"),
    ):
        page.insert_text((x, baseline), text, fontsize=11, fontname=font)
        x += pymupdf.get_text_length(text, fontname=font, fontsize=11)
    page.insert_text(
        (54, baseline + 14),
        "Exceptions require a recorded approval from the policy owner.",
        fontsize=11,
        fontname="helv",
    )
    return top + 50


def save_headings_pdf(path: Path) -> None:
    """Title, H1/H2 headings and body text across three pages.

    Page 2 starts with body text that continues section 1.1, and page 3 starts with
    a level-one heading, so heading paths must cross page breaks and only page 1 has
    a title.
    """

    spec = expectations()
    headings = spec["headings"]
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        top = _heading(page, 50, spec["title"], 26)
        top = _heading(page, top + 10, headings[0], 20)
        top = _body(page, top, "Introduction body")
        top = _heading(page, top + 10, headings[1], 14)
        top = _body(page, top, "Scope body")
        _bold_term_paragraph(page, top + 10)

        page = document.new_page(width=612, height=792)
        top = _body(page, 60, "Continued scope")
        top = _heading(page, top + 20, headings[2], 20)
        _body(page, top, "Methods body")

        page = document.new_page(width=612, height=792)
        top = _heading(page, 60, headings[3], 20)
        _body(page, top, "Results body")
        document.save(path)


def large_table_cells() -> list[str]:
    spec = expectations()["large_table"]
    cells = list(spec["header"])
    for row in range(1, spec["rows"] + 1):
        cells.extend(f"R{row:02d}C{column}" for column in range(1, spec["columns"] + 1))
    return cells


def save_large_table_pdf(path: Path) -> None:
    """A ruled table with a header row and 40 data rows on one page."""

    spec = expectations()["large_table"]
    columns = spec["columns"]
    rows = spec["rows"] + 1
    x_values = [51 + index * 85 for index in range(columns + 1)]
    y_values = [50 + index * 16 for index in range(rows + 1)]
    cells = large_table_cells()
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        for x in x_values:
            page.draw_line((x, y_values[0]), (x, y_values[-1]))
        for y in y_values:
            page.draw_line((x_values[0], y), (x_values[-1], y))
        for row in range(rows):
            for column in range(columns):
                page.insert_text(
                    (x_values[column] + 6, y_values[row] + 11),
                    cells[row * columns + column],
                    fontsize=8,
                )
        document.save(path)


def save_ocr_paragraph_pdf(path: Path) -> None:
    """An image-only page holding one paragraph that wraps over several lines."""

    text = expectations()["ocr_paragraph"]
    with pymupdf.open() as native:
        page = native.new_page(width=612, height=792)
        page.insert_textbox(pymupdf.Rect(72, 100, 420, 400), text, fontsize=18)
        image = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
        with pymupdf.open() as scanned:
            target = scanned.new_page(width=612, height=792)
            target.insert_image(target.rect, stream=image.tobytes("png"))
            scanned.save(path)


def docx_table_bytes() -> bytes:
    spec = expectations()["docx_table"]

    def cell(value: str) -> str:
        return f"<w:tc><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:tc>"

    rows = ["<w:tr>" + "".join(cell(value) for value in spec["header"]) + "</w:tr>"]
    for row in range(1, spec["rows"] + 1):
        rows.append(
            "<w:tr>"
            + "".join(cell(f"{name} {row}") for name in ("Item", "Team", "Open"))
            + "</w:tr>"
        )
    body = (
        '<w:document xmlns:w="urn:w"><w:body>'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Register</w:t></w:r></w:p>'
        f"<w:tbl>{''.join(rows)}</w:tbl>"
        "</w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", body)
    return output.getvalue()


def save_corpus(directory: Path, *, include_ocr: bool) -> dict[str, tuple[Path, str]]:
    paths = {
        "two_column": (directory / "two-column.pdf", "application/pdf"),
        "headings": (directory / "headings.pdf", "application/pdf"),
        "large_table": (directory / "large-table.pdf", "application/pdf"),
        "docx_table": (directory / "register.docx", DOCX),
    }
    save_two_column_pdf(paths["two_column"][0])
    save_headings_pdf(paths["headings"][0])
    save_large_table_pdf(paths["large_table"][0])
    paths["docx_table"][0].write_bytes(docx_table_bytes())
    if include_ocr:
        paths["ocr_paragraph"] = (directory / "ocr-paragraph.pdf", "application/pdf")
        save_ocr_paragraph_pdf(paths["ocr_paragraph"][0])
    return paths


def extract(path: Path, media_type: str, settings: ExtractNodeV2):
    return extraction.extract_document(path, media_type, path.name, settings)[0]


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / max(1, denominator) * 100, 3)


def reading_order_percent(document: ExtractedDocumentV1) -> float:
    """Share of reviewed paragraph pairs that appear in the reviewed order."""

    text = "\n".join(block.text for block in document.blocks)
    markers = expectations()["two_column_order"]
    positions = [text.index(marker) for marker in markers]
    pairs = [
        positions[left] < positions[right]
        for left in range(len(positions))
        for right in range(left + 1, len(positions))
    ]
    return _percent(sum(pairs), len(pairs))


def heading_metrics(document: ExtractedDocumentV1) -> dict[str, float | int]:
    spec = expectations()
    expected = {spec["title"], *spec["headings"]}
    detected = [
        _normalized(block.text)
        for block in document.blocks
        if block.type in {"title", "heading"}
    ]
    correct = sum(value in expected for value in detected)
    found = sum(value in detected for value in expected)
    paths_correct = 0
    for marker, path in spec["heading_paths"].items():
        block = next((value for value in document.blocks if marker in value.text), None)
        paths_correct += int(block is not None and list(block.heading_path) == path)
    return {
        "heading_precision_percent": _percent(correct, len(detected)),
        "heading_recall_percent": _percent(found, len(expected)),
        "title_blocks": sum(block.type == "title" for block in document.blocks),
        "heading_path_coverage_percent": _percent(
            paths_correct, len(spec["heading_paths"])
        ),
    }


def table_metrics(document: ExtractedDocumentV1) -> dict[str, float | int | str]:
    expected = large_table_cells()
    observed = {
        cell
        for block in document.blocks
        if block.type == "table"
        for row in block.attributes.get("table", {}).get("rows", [])
        for cell in row
    }
    return {
        "large_table_cell_retention_percent": _percent(
            sum(cell in observed for cell in expected), len(expected)
        ),
        "large_table_malformed_count": document.measurements.malformed_table_count,
        "large_table_decision": document.measurements.quality_decision,
    }


def docx_header_coverage_percent(document: ExtractedDocumentV1) -> float:
    header = expectations()["docx_table"]["header"]
    tables = [block for block in document.blocks if block.type == "table"]
    data = [block for block in tables if "Item " in block.text]
    with_header = sum(all(value in block.text for value in header) for block in data)
    return _percent(with_header, len(data))


def ocr_blocks_for_paragraph(document: ExtractedDocumentV1) -> int:
    words = set(expectations()["ocr_paragraph"].lower().split())
    return sum(
        1
        for block in document.blocks
        if block.attributes.get("origin") == "ocr"
        and words & set(block.text.lower().split())
    )


def measure_extract_corpus(
    directory: Path, *, config_version: str = "layout-ocr-v1", include_ocr: bool
) -> dict[str, float | int | str]:
    """Measure every Extract-quality fixture under one configuration version."""

    paths = save_corpus(directory, include_ocr=include_ocr)
    report: dict[str, float | int | str] = {}
    for strategy in ("auto", "layout_aware"):
        settings = extract_settings(strategy, config_version)
        two_column = extract(*paths["two_column"], settings)
        report[f"{strategy}_reading_order_percent"] = reading_order_percent(two_column)
        headings = extract(*paths["headings"], settings)
        report.update(
            {
                f"{strategy}_{key}": value
                for key, value in heading_metrics(headings).items()
            }
        )
        table = extract(*paths["large_table"], settings)
        report.update(
            {f"{strategy}_{key}": value for key, value in table_metrics(table).items()}
        )
    docx = extract(*paths["docx_table"], extract_settings("auto", config_version))
    report["docx_header_coverage_percent"] = docx_header_coverage_percent(docx)
    if include_ocr:
        ocr = extract(
            *paths["ocr_paragraph"],
            extract_settings(
                "auto",
                config_version,
                ocr={
                    "mode": "always",
                    "languages": ["eng"],
                    "rotate_pages": False,
                    "deskew": False,
                },
            ),
        )
        report["ocr_blocks_for_paragraph"] = ocr_blocks_for_paragraph(ocr)
    return report


def output_digest(document: ExtractedDocumentV1) -> str:
    value = document.model_dump(
        mode="json", exclude={"measurements": {"extraction_duration_ms"}}
    )
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def output_digests(
    directory: Path, *, config_version: str = "layout-ocr-v1"
) -> dict[str, str]:
    """SHA-256 of each non-OCR fixture's extracted document, per strategy."""

    paths = save_corpus(directory, include_ocr=False)
    digests = {}
    for name, (path, media_type) in paths.items():
        for strategy in ("auto", "native", "layout_aware"):
            document = extract(
                path, media_type, extract_settings(strategy, config_version)
            )
            digests[f"{name}/{strategy}"] = output_digest(document)
    return digests
