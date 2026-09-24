"""Bounded native, layout-aware and OCR extraction for schema-v2 artifacts."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import statistics
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import pymupdf
from PIL import Image
from pypdf import PdfReader, __version__ as pypdf_version

from app.ingestion_content.canonical import (
    CanonicalInputSegment,
    build_extracted_document,
)
from app.ingestion_content.contracts import (
    BoundingBox,
    ExtractedDocumentV1,
    QualityFinding,
)
from app.ingestion_content.processing import IngestionStageError, NativeTextExtractor
from app.ingestion_content.quality import evaluate_quality, measured_document
from app.pipelines.parsing import (
    MAX_CHARACTERS,
    MAX_PAGES,
    ProcessingError,
    validate_text,
)


LAYOUT_OCR_EXTRACTOR_VERSION = (
    f"pypdf-{pypdf_version}/pymupdf-{pymupdf.VersionBind}/tesseract-cli-v1"
)
MAX_OCR_PIXELS_PER_PAGE = 20_000_000
MAX_OCR_OUTPUT_BYTES = 5_000_000
MAX_LAYOUT_BLOCKS_PER_PAGE = 10_000
MAX_TABLE_CELLS = 100
MAX_TABLE_CELL_CHARACTERS = 160
_LIST_PREFIX = re.compile(r"^(?:[-•◦⁃] |\(?\d{1,4}[.)] )")


class OcrSettings(Protocol):
    mode: str
    languages: list[str]
    rotate_pages: bool
    deskew: bool
    dpi: int
    max_pages: int
    timeout_seconds: int


class ExtractSettings(Protocol):
    strategy: str
    ocr: OcrSettings
    tables: str
    quality_policy: str
    config_version: str


def detect_media_type(path: Path) -> str:
    """Return the supported media type from bounded bytes, never from a suffix."""

    with path.open("rb") as source:
        prefix = source.read(8192)
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    try:
        validate_text(
            prefix if path.stat().st_size <= len(prefix) else path.read_bytes()
        )
    except ProcessingError as exc:
        raise IngestionStageError(
            "extract",
            "unsupported_media_type",
            "The artifact bytes are not a supported PDF or UTF-8 TXT document.",
        ) from exc
    return "text/plain"


def _tesseract_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OMP_THREAD_LIMIT": "1",
    }


def _run_tesseract(
    args: list[str],
    *,
    timeout: int,
    stdout: int | None = subprocess.DEVNULL,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env=_tesseract_environment(),
        )
    except FileNotFoundError as exc:
        raise IngestionStageError(
            "extract",
            "ocr_unavailable",
            "The configured local OCR engine is unavailable.",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise IngestionStageError(
            "extract",
            "ocr_timeout",
            "OCR exceeded the configured per-page timeout.",
        ) from exc


def installed_ocr_languages() -> list[str]:
    try:
        result = _run_tesseract(
            ["tesseract", "--list-langs"], timeout=5, stdout=subprocess.PIPE
        )
    except IngestionStageError:
        return []
    if result.returncode != 0:
        return []
    return sorted(
        line.strip()
        for line in result.stdout.splitlines()[1:]
        if line.strip() and line.strip() != "osd" and len(line.strip()) <= 16
    )


def extraction_capabilities() -> dict[str, Any]:
    from app.ingestion_content.cleaning import default_structure_steps
    from app.ingestion_content.tokenizers import tokenizer_capabilities

    languages = installed_ocr_languages()
    return {
        "schema_version": 1,
        "media_types": ["application/pdf", "text/plain"],
        "profiles": [
            {"id": "auto", "available": True, "reason": None},
            {"id": "native", "available": True, "reason": None},
            {"id": "layout_aware", "available": True, "reason": None},
        ],
        "ocr": {
            "available": bool(languages),
            "languages": languages,
            "reason": None
            if languages
            else "No local Tesseract language packs are installed.",
            "max_pages": 100,
            "max_pixels_per_page": MAX_OCR_PIXELS_PER_PAGE,
        },
        "table_modes": ["preserve", "markdown", "plain_text"],
        "quality_policies": [
            {
                "id": "default-v1",
                "name": "Balanced",
                "description": "Rejects unsafe extraction and permits explicitly reviewed warnings.",
                "settings": {
                    "id": "default-v1",
                    "warning_action": "publish",
                    "failed_item_action": "fail",
                    "thresholds": {},
                },
            },
            {
                "id": "strict-v1",
                "name": "Strict",
                "description": "Uses tighter text, layout and OCR thresholds and blocks warnings.",
                "settings": {
                    "id": "strict-v1",
                    "warning_action": "fail",
                    "failed_item_action": "fail",
                    "thresholds": {
                        "maximum_empty_page_ratio": 0,
                        "maximum_replacement_character_ratio": 0.001,
                        "maximum_control_character_ratio": 0,
                        "minimum_ocr_confidence": 70,
                        "fail_on_suspicious_reading_order": True,
                        "fail_on_malformed_tables": True,
                    },
                },
            },
            {
                "id": "warn-v1",
                "name": "Review warnings",
                "description": "Keeps bounded quality anomalies visible for explicit review.",
                "settings": {
                    "id": "warn-v1",
                    "warning_action": "publish",
                    "failed_item_action": "exclude",
                    "thresholds": {},
                },
            },
        ],
        "cleaning_profiles": [
            {
                "id": "structure-aware-v1",
                "name": "Structure-aware standard",
                "config_version": "structure-clean-v1",
                "steps": default_structure_steps(),
            }
        ],
        "tokenizers": tokenizer_capabilities(),
        "chunking_profiles": [
            {
                "id": "section_token",
                "name": "Section-aware tokens",
                "description": "Keeps headings and compatible blocks together with a strict token ceiling.",
                "recommended": True,
                "settings": {
                    "tokenizer_version": "utf8-byte-v1",
                    "target_tokens": 600,
                    "maximum_tokens": 800,
                    "overlap_tokens": 80,
                    "add_heading_context": True,
                    "config_version": "section-token-v1",
                },
            },
            {
                "id": "parent_child",
                "name": "Parent and child",
                "description": "Embeds focused child chunks and supplies their larger saved parent as evidence.",
                "recommended": False,
                "settings": {
                    "tokenizer_version": "utf8-byte-v1",
                    "child_target_tokens": 240,
                    "child_maximum_tokens": 320,
                    "child_overlap_tokens": 40,
                    "parent_target_tokens": 900,
                    "parent_maximum_tokens": 1200,
                    "add_heading_context": True,
                    "config_version": "parent-child-v1",
                },
            },
            {
                "id": "character_window",
                "name": "Character window (compatibility)",
                "description": "Preserves the historical fixed-character window behavior.",
                "recommended": False,
                "settings": {
                    "size": 800,
                    "overlap": 120,
                    "config_version": "character-window-v1",
                },
            },
        ],
    }


def extractor_version_for_settings(settings: ExtractSettings) -> str:
    return (
        NativeTextExtractor.version
        if settings.config_version == "native-text-v1"
        else LAYOUT_OCR_EXTRACTOR_VERSION
    )


def _normalized_box(
    box: tuple[float, float, float, float] | list[float],
    width: float,
    height: float,
) -> BoundingBox | None:
    if width <= 0 or height <= 0 or len(box) != 4:
        return None
    left, top, right, bottom = (
        max(0.0, min(1.0, float(box[0]) / width)),
        max(0.0, min(1.0, float(box[1]) / height)),
        max(0.0, min(1.0, float(box[2]) / width)),
        max(0.0, min(1.0, float(box[3]) / height)),
    )
    if right - left <= 1e-7 or bottom - top <= 1e-7:
        return None
    return BoundingBox(left=left, top=top, right=right, bottom=bottom)


def _intersects(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )


def _block_text(block: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    lines = []
    spans = []
    for line in block.get("lines", []):
        value = "".join(str(span.get("text", "")) for span in line.get("spans", []))
        if value:
            lines.append(value)
        spans.extend(line.get("spans", []))
    return "\n".join(lines).strip(), spans


def _reading_order(
    blocks: list[dict[str, Any]], width: float
) -> tuple[list[dict[str, Any]], bool]:
    usable = [block for block in blocks if block.get("bbox")]
    narrow = [
        block
        for block in usable
        if float(block["bbox"][2]) - float(block["bbox"][0]) < width * 0.62
    ]
    left = [block for block in narrow if sum(block["bbox"][::2]) / 2 < width / 2]
    right = [block for block in narrow if sum(block["bbox"][::2]) / 2 >= width / 2]
    separated = (
        len(left) >= 2
        and len(right) >= 2
        and max(float(block["bbox"][2]) for block in left)
        < min(float(block["bbox"][0]) for block in right) + width * 0.04
    )
    if not separated:
        return sorted(
            usable, key=lambda block: (block["bbox"][1], block["bbox"][0])
        ), False
    column_top = min(float(block["bbox"][1]) for block in narrow)
    column_bottom = max(float(block["bbox"][3]) for block in narrow)
    before = [
        block
        for block in usable
        if block not in narrow and float(block["bbox"][3]) <= column_top
    ]
    after = [
        block
        for block in usable
        if block not in narrow and float(block["bbox"][1]) >= column_bottom
    ]
    middle = [
        block
        for block in usable
        if block not in before and block not in after and block not in narrow
    ]
    ordered = (
        sorted(before, key=lambda block: (block["bbox"][1], block["bbox"][0]))
        + sorted(left, key=lambda block: (block["bbox"][1], block["bbox"][0]))
        + sorted(right, key=lambda block: (block["bbox"][1], block["bbox"][0]))
        + sorted(middle + after, key=lambda block: (block["bbox"][1], block["bbox"][0]))
    )
    return ordered, bool(middle)


def _classify_block(
    text: str,
    spans: list[dict[str, Any]],
    *,
    body_size: float,
    top: float,
    bottom: float,
    page_height: float,
    ordinal: int,
) -> str:
    sizes = [float(span.get("size", body_size)) for span in spans if span.get("text")]
    size = statistics.median(sizes) if sizes else body_size
    fonts = " ".join(str(span.get("font", "")).lower() for span in spans)
    flags = [int(span.get("flags", 0)) for span in spans]
    if ordinal == 0 and size >= body_size * 1.65 and len(text) <= 300:
        return "title"
    if (size >= body_size * 1.25 or any(flag & 16 for flag in flags)) and len(
        text
    ) <= 500:
        return "heading"
    if _LIST_PREFIX.match(text):
        return "list_item"
    if "courier" in fonts or "mono" in fonts:
        return "code"
    if re.match(r"^(?:figure|fig\.|table)\s+\d", text, re.IGNORECASE):
        return "image_caption"
    if size <= body_size * 0.82 and top >= page_height * 0.72:
        return "footnote"
    if text.startswith(">"):
        return "quote"
    return "paragraph"


def _safe_table(rows: list[list[Any]], mode: str) -> tuple[str, dict[str, Any], bool]:
    row_count = len(rows)
    column_count = max((len(row) for row in rows), default=0)
    bounded: list[list[str]] = []
    cell_count = 0
    truncated = False
    for row in rows[:25]:
        next_row = []
        for cell in row[:10]:
            if cell_count >= MAX_TABLE_CELLS:
                truncated = True
                break
            value = "" if cell is None else str(cell)
            if len(value) > MAX_TABLE_CELL_CHARACTERS:
                value = value[:MAX_TABLE_CELL_CHARACTERS]
                truncated = True
            next_row.append(value)
            cell_count += 1
        bounded.append(next_row)
        if cell_count >= MAX_TABLE_CELLS:
            break
    truncated = truncated or row_count > len(bounded) or column_count > 10
    width = max((len(row) for row in bounded), default=0)
    normalized = [row + [""] * (width - len(row)) for row in bounded]

    def markdown_cell(value: str) -> str:
        return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")

    markdown = ""
    if normalized and width:
        escaped = [[markdown_cell(cell) for cell in row] for row in normalized]
        markdown_lines = ["| " + " | ".join(escaped[0]) + " |"]
        markdown_lines.append("| " + " | ".join(["---"] * width) + " |")
        markdown_lines.extend("| " + " | ".join(row) + " |" for row in escaped[1:])
        markdown = "\n".join(markdown_lines)
    plain = "\n".join(
        "\t".join(cell.replace("\t", " ") for cell in row) for row in normalized
    )
    evidence = plain if mode == "plain_text" else markdown
    attributes = {
        "origin": "layout",
        "engine": "pymupdf",
        "table": {
            "rows": normalized,
            "row_count": row_count,
            "column_count": column_count,
            "truncated": truncated,
            "header_row": normalized[0] if normalized else [],
        },
        "markdown": markdown,
        "plain_text": plain,
        "evidence_rendering": "plain_text" if mode == "plain_text" else "markdown",
    }
    while (
        len(json.dumps(attributes, ensure_ascii=True).encode()) > 15_500 and normalized
    ):
        normalized.pop()
        truncated = True
        attributes["table"]["rows"] = normalized
        attributes["table"]["truncated"] = True
        plain = "\n".join("\t".join(row) for row in normalized)
        attributes["plain_text"] = plain
        attributes["markdown"] = ""
        evidence = plain
        attributes["evidence_rendering"] = "plain_text"
    return evidence or "[Empty table]", attributes, truncated


def _layout_page(
    page: pymupdf.Page,
    *,
    page_number: int,
    table_mode: str,
) -> tuple[list[CanonicalInputSegment], int, int, bool]:
    width, height = float(page.rect.width), float(page.rect.height)
    dictionary = page.get_text("dict", sort=False)
    raw_blocks = [
        block for block in dictionary.get("blocks", []) if block.get("type") == 0
    ]
    if len(raw_blocks) > MAX_LAYOUT_BLOCKS_PER_PAGE:
        raise IngestionStageError(
            "extract",
            "layout_block_limit",
            "A PDF page exceeds the 10,000 layout-block safety limit.",
        )
    span_sizes = [
        float(span.get("size", 0))
        for block in raw_blocks
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text") and float(span.get("size", 0)) > 0
    ]
    body_size = statistics.median(span_sizes) if span_sizes else 11.0
    table_boxes: list[tuple[float, float, float, float]] = []
    tables: list[tuple[list[list[Any]], tuple[float, float, float, float]]] = []
    malformed = 0
    try:
        finder = page.find_tables()
        for table in finder.tables:
            rows = table.extract()
            box = tuple(float(value) for value in table.bbox)
            tables.append((rows, box))
            table_boxes.append(box)
    except Exception:
        malformed += 1
    text_blocks = [
        block
        for block in raw_blocks
        if not any(
            _intersects(tuple(block["bbox"]), table_box) for table_box in table_boxes
        )
    ]
    ordered, suspicious = _reading_order(text_blocks, width)
    segments: list[CanonicalInputSegment] = []
    for ordinal, block in enumerate(ordered):
        text, spans = _block_text(block)
        if not text:
            continue
        box = tuple(float(value) for value in block["bbox"])
        segments.append(
            CanonicalInputSegment(
                text=text,
                page_number=page_number,
                block_type=_classify_block(
                    text,
                    spans,
                    body_size=body_size,
                    top=box[1],
                    bottom=box[3],
                    page_height=height,
                    ordinal=ordinal,
                ),
                bounding_box=_normalized_box(box, width, height),
                attributes={"origin": "layout", "engine": "pymupdf"},
            )
        )
    for rows, box in sorted(tables, key=lambda value: (value[1][1], value[1][0])):
        evidence, attributes, truncated = _safe_table(rows, table_mode)
        malformed += int(truncated)
        segments.append(
            CanonicalInputSegment(
                text=evidence,
                page_number=page_number,
                block_type="table",
                bounding_box=_normalized_box(box, width, height),
                attributes=attributes,
            )
        )
    segments.sort(
        key=lambda item: (
            item.bounding_box.top if item.bounding_box else 2.0,
            item.bounding_box.left if item.bounding_box else 2.0,
        )
    )
    return segments, len(tables), malformed, suspicious


def _orientation_degrees(image_path: Path, timeout: int) -> int:
    result = _run_tesseract(
        ["tesseract", str(image_path), "stdout", "--psm", "0"],
        timeout=min(timeout, 10),
        stdout=subprocess.PIPE,
    )
    if result.returncode != 0:
        return 0
    match = re.search(r"^Rotate:\s*(0|90|180|270)\s*$", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else 0


def _deskew_angle(image: Image.Image) -> float:
    sample = image.convert("L")
    sample.thumbnail((1200, 1200))
    best_angle = 0.0
    best_score = -1.0
    for step in range(-6, 7):
        angle = step * 0.5
        rotated = sample.rotate(angle, expand=False, fillcolor=255)
        width, height = rotated.size
        pixels = rotated.load()
        rows = [
            sum(1 for x in range(0, width, 3) if pixels[x, y] < 180)
            for y in range(0, height, 2)
        ]
        score = statistics.pvariance(rows) if len(rows) > 1 else 0
        if score > best_score:
            best_angle, best_score = angle, score
    return best_angle if abs(best_angle) >= 0.5 else 0.0


def _ocr_page(
    page: pymupdf.Page,
    *,
    page_number: int,
    settings: OcrSettings,
) -> tuple[list[CanonicalInputSegment], float | None, int, float]:
    width_pixels = math.ceil(float(page.rect.width) * settings.dpi / 72)
    height_pixels = math.ceil(float(page.rect.height) * settings.dpi / 72)
    if width_pixels * height_pixels > MAX_OCR_PIXELS_PER_PAGE:
        raise IngestionStageError(
            "extract",
            "ocr_pixel_limit",
            "A PDF page exceeds the 20,000,000 pixel OCR safety limit.",
        )
    pixmap = page.get_pixmap(dpi=settings.dpi, colorspace=pymupdf.csGRAY, alpha=False)
    image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("L")
    rotation = 0
    deskew = 0.0
    with tempfile.TemporaryDirectory(prefix="rqs-ocr-") as directory:
        root = Path(directory)
        input_path = root / "page.png"
        image.save(input_path, format="PNG", optimize=False)
        if settings.rotate_pages:
            rotation = _orientation_degrees(input_path, settings.timeout_seconds)
            if rotation:
                # Tesseract reports the clockwise correction required, while Pillow's
                # positive angles rotate counter-clockwise.
                image = image.rotate(-rotation, expand=True, fillcolor=255)
        if settings.deskew:
            deskew = _deskew_angle(image)
            if deskew:
                image = image.rotate(deskew, expand=True, fillcolor=255)
        image.save(input_path, format="PNG", optimize=False)
        output_base = root / "result"
        language = "+".join(settings.languages)
        result = _run_tesseract(
            [
                "tesseract",
                str(input_path),
                str(output_base),
                "-l",
                language,
                "--dpi",
                str(settings.dpi),
                "--psm",
                "3",
                "tsv",
            ],
            timeout=settings.timeout_seconds,
        )
        if result.returncode != 0:
            raise IngestionStageError(
                "extract",
                "ocr_failed",
                "The local OCR engine could not process a PDF page.",
            )
        output_path = output_base.with_suffix(".tsv")
        if (
            not output_path.exists()
            or output_path.stat().st_size > MAX_OCR_OUTPUT_BYTES
        ):
            raise IngestionStageError(
                "extract",
                "ocr_output_limit",
                "OCR output exceeded the bounded per-page result limit.",
            )
        rows = list(
            csv.DictReader(
                output_path.read_text(errors="replace").splitlines(), delimiter="\t"
            )
        )

    groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    confidences: list[float] = []
    for row in rows:
        text = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf") or -1)
        except ValueError:
            confidence = -1
        if not text or confidence < 0:
            continue
        confidences.append(confidence)
        key = (
            row.get("block_num", "0"),
            row.get("par_num", "0"),
            row.get("line_num", "0"),
        )
        groups.setdefault(key, []).append(row)
    image_width, image_height = image.size
    segments = []
    for group in groups.values():
        text = " ".join((row.get("text") or "").strip() for row in group).strip()
        if not text:
            continue
        left = min(int(row.get("left") or 0) for row in group)
        top = min(int(row.get("top") or 0) for row in group)
        right = max(
            int(row.get("left") or 0) + int(row.get("width") or 0) for row in group
        )
        bottom = max(
            int(row.get("top") or 0) + int(row.get("height") or 0) for row in group
        )
        group_confidence = statistics.mean(float(row.get("conf") or 0) for row in group)
        segments.append(
            CanonicalInputSegment(
                text=text,
                page_number=page_number,
                block_type="paragraph",
                bounding_box=_normalized_box(
                    (left, top, right, bottom), image_width, image_height
                ),
                attributes={
                    "origin": "ocr",
                    "engine": "tesseract",
                    "engine_confidence": round(group_confidence, 3),
                    "languages": list(settings.languages),
                    "rotation_applied": rotation,
                    "deskew_degrees": deskew,
                },
            )
        )
    segments.sort(
        key=lambda item: (
            item.bounding_box.top if item.bounding_box else 2.0,
            item.bounding_box.left if item.bounding_box else 2.0,
        )
    )
    return (
        segments,
        statistics.median(confidences) if confidences else None,
        rotation,
        deskew,
    )


def _native_pages(path: Path) -> list[str]:
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise IngestionStageError(
                "extract",
                "encrypted_pdf",
                "Encrypted PDFs are unsupported. Upload an unencrypted PDF.",
            )
        count = len(reader.pages)
        if count == 0 or count > MAX_PAGES:
            raise IngestionStageError(
                "extract",
                "pdf_page_limit",
                "PDF must contain between 1 and 2,000 pages.",
            )
        values = []
        total = 0
        for page in reader.pages:
            value = page.extract_text() or ""
            if "\x00" in value:
                raise IngestionStageError(
                    "extract",
                    "unsupported_control_character",
                    "PDF text contains unsupported null characters.",
                )
            total += len(value)
            if total > MAX_CHARACTERS:
                raise IngestionStageError(
                    "extract",
                    "character_limit",
                    "Document exceeds the 5,000,000 character processing limit.",
                )
            values.append(value)
        return values
    except IngestionStageError:
        raise
    except Exception as exc:
        raise IngestionStageError(
            "extract",
            "malformed_pdf",
            "PDF could not be parsed as a valid, unencrypted document.",
        ) from exc


def _text_document(path: Path, title: str | None) -> ExtractedDocumentV1:
    try:
        segments = list(NativeTextExtractor().extract(path, "text/plain"))
    except ProcessingError as exc:
        raise IngestionStageError("extract", "extraction_failed", str(exc)) from exc
    document = build_extracted_document(
        segments,
        media_type="text/plain",
        title=title,
        page_metadata={},
    )
    return measured_document(document, duration_ms=0)


def extract_document(
    path: Path,
    declared_media_type: str,
    title: str | None,
    settings: ExtractSettings,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[ExtractedDocumentV1, str]:
    """Extract one artifact with exact page-level origin and bounded fallback rules."""

    started = time.monotonic()
    detected = detect_media_type(path)
    if detected != declared_media_type:
        raise IngestionStageError(
            "extract",
            "media_type_mismatch",
            "Artifact bytes do not match the stored media type.",
        )
    if detected == "text/plain":
        document = evaluate_quality(
            _text_document(path, title), settings.quality_policy
        )
        return document, NativeTextExtractor.version
    if settings.config_version == "native-text-v1":
        try:
            segments = list(NativeTextExtractor().extract(path, detected))
        except ProcessingError as exc:
            raise IngestionStageError("extract", "extraction_failed", str(exc)) from exc
        document = build_extracted_document(segments, media_type=detected, title=title)
        return document, NativeTextExtractor.version

    available_languages = set(installed_ocr_languages())
    if (
        settings.ocr.mode != "off"
        and not set(settings.ocr.languages) <= available_languages
    ):
        raise IngestionStageError(
            "extract",
            "ocr_language_unavailable",
            "One or more selected OCR language packs are unavailable.",
        )
    native_pages = _native_pages(path)
    try:
        pdf = pymupdf.open(path)
    except Exception as exc:
        raise IngestionStageError(
            "extract", "malformed_pdf", "The layout adapter could not open the PDF."
        ) from exc
    if pdf.needs_pass:
        pdf.close()
        raise IngestionStageError(
            "extract", "encrypted_pdf", "Encrypted PDFs are unsupported."
        )
    if pdf.page_count != len(native_pages):
        pdf.close()
        raise IngestionStageError(
            "extract",
            "page_count_mismatch",
            "PDF parsers disagreed on the bounded page count.",
        )

    segments: list[CanonicalInputSegment] = []
    metadata: dict[int, dict[str, Any]] = {}
    findings: list[QualityFinding] = []
    table_count = 0
    malformed_tables = 0
    suspicious_order = 0
    ocr_pages = 0
    try:
        for index, native_text in enumerate(native_pages):
            if cancelled and cancelled():
                raise IngestionStageError(
                    "extract", "cancelled", "Extraction was cancelled between pages."
                )
            page_number = index + 1
            page = pdf.load_page(index)
            width, height = float(page.rect.width), float(page.rect.height)
            origin = "native"
            fallback_reason = None
            confidence = None
            rotation = int(page.rotation) % 360
            page_segments: list[CanonicalInputSegment]
            native_characters = len(native_text.strip())
            use_ocr = settings.ocr.mode == "always"
            if not use_ocr and native_characters < 20 and settings.ocr.mode == "auto":
                use_ocr = True
                fallback_reason = "native_text_below_20_characters"
            if use_ocr:
                ocr_pages += 1
                if ocr_pages > settings.ocr.max_pages:
                    raise IngestionStageError(
                        "extract",
                        "ocr_page_limit",
                        "OCR exceeded the configured document page limit.",
                    )
                page_segments, confidence, applied_rotation, _ = _ocr_page(
                    page, page_number=page_number, settings=settings.ocr
                )
                rotation = (rotation + applied_rotation) % 360
                origin = "ocr"
                fallback_reason = fallback_reason or "ocr_always"
            elif settings.strategy == "native":
                page_segments = (
                    [
                        CanonicalInputSegment(
                            text=native_text,
                            page_number=page_number,
                            attributes={"origin": "native", "engine": "pypdf"},
                        )
                    ]
                    if native_text
                    else []
                )
            else:
                layout_segments, page_tables, page_malformed, page_suspicious = (
                    _layout_page(
                        page, page_number=page_number, table_mode=settings.tables
                    )
                )
                layout_characters = sum(len(item.text) for item in layout_segments)
                multi_column = (
                    len(
                        {
                            round(
                                (item.bounding_box.left if item.bounding_box else 0) * 4
                            )
                            for item in layout_segments
                            if item.bounding_box
                            and item.bounding_box.right - item.bounding_box.left < 0.62
                        }
                    )
                    >= 2
                )
                use_layout = settings.strategy == "layout_aware"
                reason = "layout_profile"
                if settings.strategy == "auto":
                    if page_tables:
                        use_layout, reason = True, "table_detected"
                    elif multi_column:
                        use_layout, reason = True, "multiple_columns_detected"
                    elif (
                        native_characters
                        and abs(layout_characters - native_characters)
                        / max(native_characters, 1)
                        > 0.25
                    ):
                        use_layout, reason = True, "native_layout_character_delta"
                    else:
                        use_layout = False
                if use_layout:
                    page_segments = layout_segments
                    origin = "layout"
                    fallback_reason = reason
                    table_count += page_tables
                    malformed_tables += page_malformed
                    suspicious_order += int(page_suspicious)
                else:
                    page_segments = (
                        [
                            CanonicalInputSegment(
                                text=native_text,
                                page_number=page_number,
                                attributes={"origin": "native", "engine": "pypdf"},
                            )
                        ]
                        if native_text
                        else []
                    )
            if not page_segments and settings.ocr.mode == "off":
                findings.append(
                    QualityFinding(
                        code="ocr_required",
                        severity="error",
                        message="A page has no native text and OCR is disabled.",
                        page_numbers=[page_number],
                        remediation="Select Automatic fallback or Always OCR.",
                    )
                )
            metadata[page_number] = {
                "origin": origin,
                "character_count": sum(len(item.text) for item in page_segments),
                "block_count": len(page_segments),
                "fallback_reason": fallback_reason,
                "width_points": width,
                "height_points": height,
                "rotation_degrees": rotation,
                "ocr_confidence": confidence,
            }
            segments.extend(page_segments)
    finally:
        pdf.close()
    document = build_extracted_document(
        segments,
        media_type=detected,
        title=title,
        page_metadata=metadata,
        findings=findings,
    )
    document = measured_document(
        document,
        duration_ms=round((time.monotonic() - started) * 1000),
        table_count=table_count,
        malformed_table_count=malformed_tables,
        suspicious_reading_order_count=suspicious_order,
    )
    return evaluate_quality(
        document, settings.quality_policy
    ), LAYOUT_OCR_EXTRACTOR_VERSION


def render_pdf_thumbnail(
    path: Path, page_number: int, *, max_width: int = 1200
) -> bytes:
    """Render a bounded annotation-free PNG for an authorized inspector request."""

    detected = detect_media_type(path)
    if detected != "application/pdf":
        raise IngestionStageError(
            "extract",
            "thumbnail_unavailable",
            "Page thumbnails are available only for PDFs.",
        )
    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass or page_number < 1 or page_number > pdf.page_count:
                raise IngestionStageError(
                    "extract",
                    "thumbnail_unavailable",
                    "The selected PDF page is unavailable.",
                )
            page = pdf.load_page(page_number - 1)
            scale = min(2.0, max_width / max(1.0, float(page.rect.width)))
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                colorspace=pymupdf.csRGB,
                alpha=False,
                annots=False,
            )
            if pixmap.width * pixmap.height > 8_000_000:
                raise IngestionStageError(
                    "extract",
                    "thumbnail_pixel_limit",
                    "The page preview exceeds its pixel limit.",
                )
            return pixmap.tobytes("png")
    except IngestionStageError:
        raise
    except Exception as exc:
        raise IngestionStageError(
            "extract", "thumbnail_unavailable", "The PDF page preview is unavailable."
        ) from exc
