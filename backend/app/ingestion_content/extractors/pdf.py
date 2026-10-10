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
from dataclasses import replace
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
from app.ingestion_content.language import apply_language_policy
from app.ingestion_content.tables import table_row_groups
from app.ingestion_content.extractors.formats import (
    FORMAT_EXTRACTOR_VERSION,
    FORMAT_V2_EXTRACTOR_VERSION,
    FORMAT_V3_EXTRACTOR_VERSION,
    STRUCTURED_MEDIA_TYPES,
    detect_structured_media_type,
    extract_structured_document,
)
from app.pipelines.parsing import (
    MAX_CHARACTERS,
    MAX_PAGES,
    ProcessingError,
    validate_text,
)


LAYOUT_OCR_EXTRACTOR_VERSION = (
    f"pypdf-{pypdf_version}/pymupdf-{pymupdf.VersionBind}/tesseract-cli-v2/"
    f"{FORMAT_EXTRACTOR_VERSION}"
)
# layout-ocr-v2 keeps the computed column reading order (plan Slice 1).
LAYOUT_OCR_V2_EXTRACTOR_VERSION = (
    f"pypdf-{pypdf_version}/pymupdf-{pymupdf.VersionBind}/tesseract-cli-v2/"
    f"layout-v2/{FORMAT_V2_EXTRACTOR_VERSION}"
)
MAX_OCR_PIXELS_PER_PAGE = 20_000_000
MAX_OCR_OUTPUT_BYTES = 5_000_000
MAX_LAYOUT_BLOCKS_PER_PAGE = 10_000
MAX_TABLE_CELLS = 100
MAX_TABLE_CELL_CHARACTERS = 160
# layout-ocr-v3 (spec 0007) also rebuilds merged-column tables from word rows.
LAYOUT_OCR_V3_EXTRACTOR_VERSION = (
    f"pypdf-{pypdf_version}/pymupdf-{pymupdf.VersionBind}/tesseract-cli-v2/"
    f"layout-v3/{FORMAT_V2_EXTRACTOR_VERSION}"
)
# layout-ocr-v4 (spec 0008) also reads sideways pages and PowerPoint tables.
LAYOUT_OCR_V4_EXTRACTOR_VERSION = (
    f"pypdf-{pypdf_version}/pymupdf-{pymupdf.VersionBind}/tesseract-cli-v2/"
    f"layout-v4/{FORMAT_V3_EXTRACTOR_VERSION}"
)
# layout-ocr-v5 (spec 0009) also reads charts as text instead of as tables.
LAYOUT_OCR_V5_EXTRACTOR_VERSION = (
    f"pypdf-{pypdf_version}/pymupdf-{pymupdf.VersionBind}/tesseract-cli-v2/"
    f"layout-v5/{FORMAT_V3_EXTRACTOR_VERSION}"
)
# Versions that share the v2 layout, heading, table and OCR behaviour.
LAYOUT_V2_FAMILY = frozenset(
    {"layout-ocr-v2", "layout-ocr-v3", "layout-ocr-v4", "layout-ocr-v5"}
)
# Versions that rebuild merged-column tables from word rows (v3 onward).
MERGED_TABLE_VERSIONS = frozenset({"layout-ocr-v3", "layout-ocr-v4", "layout-ocr-v5"})
# Versions that straighten sideways pages, rejoin soft hyphens and read slide
# tables (v4 onward).
V4_READING_VERSIONS = frozenset({"layout-ocr-v4", "layout-ocr-v5"})
# Versions that read a mostly empty detected table as a chart region (v5 onward).
CHART_REGION_VERSIONS = frozenset({"layout-ocr-v5"})
# A detected table with fewer filled cells than this share is a chart, not a table:
# real tables in the spec 0009 corpus are 45% filled or more, charts under 30%.
CHART_TABLE_MAX_FILL = 0.3
# Versions that attach a table's caption to its blocks and repeat all header lines
# of a rebuilt table (v5 onward).
TABLE_CONTEXT_VERSIONS = frozenset({"layout-ocr-v5"})
# "Table 1", "Table A-2.", "Table A-4a.", "Table 3.1:", "Tableau II" at the start
# of a block.
_TABLE_CAPTION = re.compile(
    r"^(?:Table|TABLE|Tableau|TABLEAU)\s+"
    r"(?:[A-Z]{1,3}-?\d+[a-z]?(?:[.-]\d+)*|\d+[a-z]?(?:[.-]\d+)*|[IVXLC]+)"
    r"(?:[.:—–-]|\s|$)"
)
MAX_CAPTION_CHARACTERS = 300
# Back-matter headings that run on over later tables without containing them.
_BACK_MATTER_HEADING = re.compile(
    r"^(?:end\s?notes|notes|foot\s?notes|references|bibliography|sources|"
    r"notes et sources|notes de fin|bibliographie|références)\.?$",
    re.IGNORECASE,
)
# A rebuilt table repeats at most this many header lines in each row group.
MAX_HEADER_LINES = 8
# A data value; currency amounts are left out because headers print column ranges
# such as "$15,000 to $24,999" while the rows below hold plain figures.
_NUMBER_TOKEN = re.compile(r"^[-+−(]?\d[\d.,]*[%)]?\d*[¹²³⁴⁵⁶⁷⁸⁹*]*$")
# A detected table whose cells each hold this many lines is a merged-column table.
MERGED_COLUMN_MIN_LINES = 5
# v4 reads a page straightened when most of its text runs at 90 or 270 degrees.
SIDEWAYS_TEXT_MIN_SHARE = 0.6
SIDEWAYS_TEXT_MIN_CHARACTERS = 100
# A soft hyphen (U+00AD) before a line break marks a word the typesetter broke;
# v4 rejoins it. Cleaning would otherwise drop the hyphen and leave "house holds".
_SOFT_HYPHEN_BREAK = re.compile(r"(?<=[^\W\d_])\u00ad[ \t]*\n[ \t]*(?=[^\W\d_])")
_DOT_LEADER = re.compile(r"(?:\s*\.){3,}")
# layout-ocr-v2 keeps whole tables as row groups within these safety limits.
MAX_TABLE_V2_ROWS = 2_000
MAX_TABLE_V2_COLUMNS = 50
MAX_TABLE_V2_CELL_CHARACTERS = 1_000
_LIST_PREFIX = re.compile(r"^(?:[-•◦⁃] |\(?\d{1,4}[.)] )")
# layout-ocr-v2 heading rules (plan Slice 3).
_SENTENCE_END = re.compile(r"[.!?;,]$")
_NUMBERED_HEADING = re.compile(r"^\(?\d{1,3}(?:\.\d{1,3})*[.)]?\s+\S")
_BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
MAX_HEADING_CHARACTERS = 200
MAX_HEADING_LINES = 3
MAX_HEADING_LEVELS = 6
# v2 Auto keeps layout blocks unless they hold under 75% of the native characters.
LAYOUT_TEXT_LOSS_RATIO = 0.75


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
    language_policy: object
    config_version: str


def detect_media_type(path: Path, declared_media_type: str | None = None) -> str:
    """Return the supported media type from bounded bytes, never from a suffix."""

    with path.open("rb") as source:
        prefix = source.read(8192)
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    structured = detect_structured_media_type(path, declared_media_type)
    if structured is not None:
        return structured
    try:
        validate_text(
            prefix if path.stat().st_size <= len(prefix) else path.read_bytes()
        )
    except ProcessingError as exc:
        raise IngestionStageError(
            "extract",
            "unsupported_media_type",
            "The artifact bytes are not a supported document format.",
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


OCR_LANGUAGE_CACHE_SECONDS = 300
_ocr_language_cache: tuple[float, list[str]] | None = None


def installed_ocr_languages() -> list[str]:
    """Installed Tesseract language packs, cached per process for five minutes."""

    global _ocr_language_cache
    now = time.monotonic()
    if _ocr_language_cache is not None and now < _ocr_language_cache[0]:
        return list(_ocr_language_cache[1])
    languages = _list_ocr_languages()
    _ocr_language_cache = (now + OCR_LANGUAGE_CACHE_SECONDS, languages)
    return list(languages)


def _list_ocr_languages() -> list[str]:
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
        "media_types": [
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/html",
            "text/csv",
            "text/tab-separated-values",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ],
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
                    "config_version": "section-token-v2",
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
                    "config_version": "parent-child-v2",
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
    return {
        "native-text-v1": NativeTextExtractor.version,
        "layout-ocr-v2": LAYOUT_OCR_V2_EXTRACTOR_VERSION,
        "layout-ocr-v3": LAYOUT_OCR_V3_EXTRACTOR_VERSION,
        "layout-ocr-v4": LAYOUT_OCR_V4_EXTRACTOR_VERSION,
        "layout-ocr-v5": LAYOUT_OCR_V5_EXTRACTOR_VERSION,
    }.get(settings.config_version, LAYOUT_OCR_EXTRACTOR_VERSION)


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


def _is_chart_region(rows: list[list[Any]]) -> bool:
    """A detected table with almost no filled cells is a chart's gridlines (v5)."""

    cells = sum(len(row) for row in rows)
    filled = sum(1 for row in rows for cell in row if cell and str(cell).strip())
    return cells == 0 or filled / cells < CHART_TABLE_MAX_FILL


def _overlap_share(
    box: tuple[float, float, float, float],
    region: tuple[float, float, float, float],
) -> float:
    """The share of box's area that lies inside region."""

    width = min(box[2], region[2]) - max(box[0], region[0])
    height = min(box[3], region[3]) - max(box[1], region[1])
    area = (box[2] - box[0]) * (box[3] - box[1])
    if width <= 0 or height <= 0 or area <= 0:
        return 0.0
    return width * height / area


def _in_any(
    box: tuple[float, float, float, float],
    regions: list[tuple[float, float, float, float]],
) -> bool:
    return any(_intersects(box, region) for region in regions)


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


def _bold_coverage(spans: list[dict[str, Any]]) -> float:
    total = bold = 0
    for span in spans:
        characters = len(str(span.get("text", "")).strip())
        if not characters:
            continue
        total += characters
        if int(span.get("flags", 0)) & 16 or _BOLD_FONT.search(
            str(span.get("font", ""))
        ):
            bold += characters
    return bold / total if total else 0.0


def _classify_block_v2(
    text: str,
    spans: list[dict[str, Any]],
    *,
    body_size: float,
    top: float,
    page_height: float,
) -> tuple[str, float]:
    """Classify a layout block; titles and heading levels are decided per document."""

    sizes = [float(span.get("size", body_size)) for span in spans if span.get("text")]
    size = statistics.median(sizes) if sizes else body_size
    fonts = " ".join(str(span.get("font", "")).lower() for span in spans)
    shaped_like_heading = (
        len(text) <= MAX_HEADING_CHARACTERS
        and text.count("\n") < MAX_HEADING_LINES
        and (
            not _SENTENCE_END.search(text.rstrip())
            or bool(_NUMBERED_HEADING.match(text))
        )
    )
    if shaped_like_heading and (
        size >= body_size * 1.2 or _bold_coverage(spans) >= 0.8
    ):
        return "heading", size
    if _LIST_PREFIX.match(text):
        return "list_item", size
    if "courier" in fonts or "mono" in fonts:
        return "code", size
    if re.match(r"^(?:figure|fig\.|table)\s+\d", text, re.IGNORECASE):
        return "image_caption", size
    if size <= body_size * 0.82 and top >= page_height * 0.72:
        return "footnote", size
    if text.startswith(">"):
        return "quote", size
    return "paragraph", size


def _heading_key(size: float) -> float:
    return round(size * 2) / 2


def _heading_structure(
    segments: list[CanonicalInputSegment],
) -> list[CanonicalInputSegment]:
    """Assign one title, heading levels and heading paths across the document.

    Levels rank distinct heading font sizes, largest first. The title is the first
    page-1 heading when the document has other headings and its size is larger than
    all of them; it is not part of heading paths. Paths continue across pages until a heading of the same or a
    higher level replaces them.
    """

    headings = [
        index
        for index, segment in enumerate(segments)
        if segment.block_type == "heading"
        and isinstance((segment.attributes or {}).get("font_size"), (int, float))
    ]

    def size_of(index: int) -> float:
        return _heading_key(float(segments[index].attributes["font_size"]))

    title_index = None
    first_page = [index for index in headings if segments[index].page_number == 1]
    # A lone heading stays a section heading so its paragraphs keep the path.
    if first_page and len(headings) > 1:
        candidate = first_page[0]
        if all(
            size_of(candidate) > size_of(other)
            for other in headings
            if other != candidate
        ):
            title_index = candidate
    sizes = sorted(
        {size_of(index) for index in headings if index != title_index}, reverse=True
    )
    levels = {
        size: min(rank + 1, MAX_HEADING_LEVELS) for rank, size in enumerate(sizes)
    }

    result = []
    stack: list[tuple[int, str]] = []
    for index, segment in enumerate(segments):
        attributes = dict(segment.attributes or {})
        if index == title_index:
            result.append(replace(segment, block_type="title", heading_path=()))
            continue
        if index in headings:
            level = levels[size_of(index)]
            while stack and stack[-1][0] >= level:
                stack.pop()
            attributes["heading_level"] = level
            result.append(
                replace(
                    segment,
                    heading_path=tuple(text for _, text in stack),
                    attributes=attributes,
                )
            )
            stack.append((level, " ".join(segment.text.split())[:500]))
            continue
        result.append(replace(segment, heading_path=tuple(text for _, text in stack)))
    return result


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


def _table_row_groups(
    rows: list[list[Any]],
    mode: str,
    *,
    table_id: str,
    cell_limit: int | None = MAX_TABLE_V2_CELL_CHARACTERS,
) -> tuple[list[tuple[str, dict[str, Any], int, int]], bool]:
    """v2 cuts cells at 1,000 characters; v3 keeps them whole (spec 0007, X2)."""

    return table_row_groups(
        rows,
        mode,
        table_id=table_id,
        max_rows=MAX_TABLE_V2_ROWS,
        max_columns=MAX_TABLE_V2_COLUMNS,
        max_cell_characters=cell_limit,
        base_attributes={"origin": "layout", "engine": "pymupdf"},
    )


def _overlaps_horizontally(first: BoundingBox, second: BoundingBox) -> bool:
    return first.left < second.right and second.left < first.right


def _place_tables(
    ordered: list[CanonicalInputSegment], tables: list[list[CanonicalInputSegment]]
) -> list[CanonicalInputSegment]:
    """Insert tables into a computed reading order without re-sorting the text.

    A table follows the last segment above it in the same column band. With no such
    segment it precedes the first segment below it, and otherwise ends the page. The
    row groups of one table stay together in order.
    """

    result = list(ordered)
    for groups in tables:
        if not groups:
            continue
        box = groups[0].bounding_box
        if box is None:
            result.extend(groups)
            continue
        above = [
            index
            for index, item in enumerate(result)
            if item.bounding_box is not None
            and item.bounding_box.top < box.top
            and _overlaps_horizontally(item.bounding_box, box)
        ]
        if above:
            position = above[-1] + 1
        else:
            position = next(
                (
                    index
                    for index, item in enumerate(result)
                    if item.bounding_box is not None
                    and item.bounding_box.top >= box.top
                ),
                len(result),
            )
        result[position:position] = groups
    return result


def _group_box(
    table_box: tuple[float, float, float, float],
    row_boxes: list,
    first: int,
    last: int,
) -> tuple[float, float, float, float]:
    """Union of a group's row bands, or the whole table when bands are unavailable."""

    bands = [
        tuple(float(value) for value in band)
        for band in row_boxes[first : last + 1]
        if band is not None and len(band) == 4
    ]
    if not bands or len(bands) != last - first + 1:
        return table_box
    return (
        min(band[0] for band in bands),
        min(band[1] for band in bands),
        max(band[2] for band in bands),
        max(band[3] for band in bands),
    )


def _is_data_line(line: str) -> bool:
    words = line.split()
    numbers = sum(1 for word in words if _NUMBER_TOKEN.match(word))
    return bool(words) and numbers * 2 >= len(words) and numbers >= 2


def _header_line_count(lines: list[str]) -> int:
    """How many printed lines above the first data line form the header (v5).

    Section labels in capitals ("ALL RACES") just above the data stay body rows.
    Returns 0 when no header can be told apart, so the v4 grouping is kept.
    """

    first_data = next(
        (index for index, line in enumerate(lines) if _is_data_line(line)), None
    )
    if not first_data:
        return 0
    count = first_data
    while count > 1 and lines[count - 1].isupper() and len(lines[count - 1]) <= 60:
        count -= 1
    return count if count <= MAX_HEADER_LINES else 0


def _table_captions(
    segments: list[CanonicalInputSegment],
) -> list[CanonicalInputSegment]:
    """Attach a table caption directly above a table to the table's blocks (v5).

    The caption ("Table A-2. Households by ...") becomes the last element of the
    heading path of the caption and of every block of the table that follows it on
    the same page. A notes or references heading that started on an earlier page is
    replaced, so an appendix table is not filed under "Endnotes"; any other heading
    stays, because a section's table can sit pages after its heading.
    """

    heading_pages: dict[str, int] = {}
    result = list(segments)
    for index, segment in enumerate(segments):
        if segment.block_type == "heading":
            heading_pages[" ".join(segment.text.split())[:500]] = segment.page_number
            continue
        if segment.block_type == "table" or not _TABLE_CAPTION.match(segment.text):
            continue
        following = index + 1
        table_id = None
        while following < len(segments):
            candidate = segments[following]
            if (
                candidate.block_type != "table"
                or candidate.page_number != segment.page_number
            ):
                break
            candidate_id = (candidate.attributes or {}).get("table", {}).get("table_id")
            if table_id is not None and candidate_id != table_id:
                break
            table_id = candidate_id
            following += 1
        if following == index + 1:
            continue
        # The title before any parenthesised note ("(Income in 2022 dollars ...").
        caption = " ".join(segment.text.split()).split(" (", 1)[0]
        caption = caption[:MAX_CAPTION_CHARACTERS]
        path = tuple(segment.heading_path)
        if (
            path
            and _BACK_MATTER_HEADING.match(path[-1])
            and heading_pages.get(path[-1], segment.page_number) < segment.page_number
        ):
            path = path[:-1]
        path = (*path, caption)
        result[index] = replace(segment, heading_path=path)
        for table_index in range(index + 1, following):
            table_segment = segments[table_index]
            attributes = dict(table_segment.attributes or {})
            attributes["table"] = {**attributes.get("table", {}), "caption": caption}
            result[table_index] = replace(
                table_segment, heading_path=path, attributes=attributes
            )
    return result


def _is_merged_column_table(rows: list[list[Any]]) -> bool:
    """True when PyMuPDF put whole columns of a borderless table into single cells."""

    line_counts = [str(cell).count("\n") + 1 for row in rows for cell in row if cell]
    full = [count for count in line_counts if count >= MERGED_COLUMN_MIN_LINES]
    return len(full) >= 2 and len(rows) < max(full)


def _word_rows(page: pymupdf.Page, box: tuple[float, float, float, float]) -> list[str]:
    """Printed lines inside a table area, rebuilt from word positions."""

    words = page.get_text("words", clip=pymupdf.Rect(*box))
    if not words:
        return []
    heights = sorted(float(word[3]) - float(word[1]) for word in words)
    tolerance = max(1.0, heights[len(heights) // 2] * 0.5)
    lines: list[list[tuple[float, float, str]]] = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        centre = (float(word[1]) + float(word[3])) / 2
        if lines and abs(lines[-1][-1][0] - centre) <= tolerance:
            lines[-1].append((centre, float(word[0]), str(word[4])))
        else:
            lines.append([(centre, float(word[0]), str(word[4]))])
    result = []
    for line in lines:
        text = " ".join(word for _, _, word in sorted(line, key=lambda w: w[1]))
        text = " ".join(_DOT_LEADER.sub(" ", text).split())
        if text:
            result.append(text)
    return result


def _sideways_rotation(page: pymupdf.Page) -> int:
    """270 when most text reads bottom to top, 90 when top to bottom, else 0.

    The angle is the clockwise turn that makes the text horizontal. Landscape tables
    printed on portrait pages, such as Census P60-279 pp. 22-36, read bottom to top.
    """

    characters = {0: 0, 90: 0, 270: 0}
    for block in page.get_text("dict", sort=False).get("blocks", []):
        for line in block.get("lines", []):
            count = sum(
                len(span.get("text", "").strip()) for span in line.get("spans", [])
            )
            dx, dy = line.get("dir", (1.0, 0.0))
            if abs(dx) < 0.1 and abs(dy) > 0.9:
                characters[270 if dy < 0 else 90] += count
            else:
                characters[0] += count
    total = sum(characters.values())
    rotation = max((90, 270), key=lambda angle: characters[angle])
    if total >= SIDEWAYS_TEXT_MIN_CHARACTERS and (
        characters[rotation] >= total * SIDEWAYS_TEXT_MIN_SHARE
    ):
        return rotation
    return 0


def _straightened_page(
    page: pymupdf.Page, rotation: int
) -> tuple[pymupdf.Document, pymupdf.Page]:
    """A one-page copy turned so sideways text reads left to right."""

    document = pymupdf.open()
    straight = document.new_page(
        width=float(page.rect.height), height=float(page.rect.width)
    )
    straight.show_pdf_page(straight.rect, page.parent, page.number, rotate=rotation)
    return document, straight


def _unrotated_box(box: BoundingBox | None, rotation: int) -> BoundingBox | None:
    """Map a normalized box on a straightened page back onto the original page."""

    if box is None:
        return None
    if rotation == 270:
        return BoundingBox(
            left=box.top, top=1 - box.right, right=box.bottom, bottom=1 - box.left
        )
    return BoundingBox(
        left=1 - box.bottom, top=box.left, right=1 - box.top, bottom=box.right
    )


def _layout_page(
    page: pymupdf.Page,
    *,
    page_number: int,
    table_mode: str,
    layout_v2: bool = False,
    rebuild_merged_tables: bool = False,
    chart_regions: bool = False,
    table_context: bool = False,
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
    chart_boxes: list[tuple[float, float, float, float]] = []
    tables: list[tuple[list[list[Any]], tuple[float, float, float, float], list]] = []
    malformed = 0
    try:
        finder = page.find_tables()
        for table in finder.tables:
            rows = table.extract()
            box = tuple(float(value) for value in table.bbox)
            if chart_regions and _is_chart_region(rows):
                # v5: chart gridlines are not a table; its text is read as layout blocks.
                chart_boxes.append(box)
                continue
            # Row bands give each v2 row group its own inspector geometry.
            row_boxes = (
                [getattr(row, "bbox", None) for row in table.rows] if layout_v2 else []
            )
            tables.append((rows, box, row_boxes))
            table_boxes.append(box)
    except Exception:
        malformed += 1
    if chart_boxes:
        # A small table drawn inside a chart (a legend box, a figure label) is part
        # of the chart, so the chart's text is not cut where it overlaps.
        inside = [
            index
            for index, (_, box, _) in enumerate(tables)
            if any(_overlap_share(box, chart) >= 0.5 for chart in chart_boxes)
        ]
        chart_boxes.extend(tables[index][1] for index in inside)
        tables = [table for index, table in enumerate(tables) if index not in inside]
        table_boxes = [box for _, box, _ in tables]
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
        attributes: dict[str, Any] = {"origin": "layout", "engine": "pymupdf"}
        if _in_any(box, chart_boxes):
            attributes["chart_region"] = True
        if layout_v2:
            block_type, size = _classify_block_v2(
                text, spans, body_size=body_size, top=box[1], page_height=height
            )
            if block_type == "heading":
                attributes["font_size"] = round(size, 2)
        else:
            block_type = _classify_block(
                text,
                spans,
                body_size=body_size,
                top=box[1],
                bottom=box[3],
                page_height=height,
                ordinal=ordinal,
            )
        segments.append(
            CanonicalInputSegment(
                text=text,
                page_number=page_number,
                block_type=block_type,
                bounding_box=_normalized_box(box, width, height),
                attributes=attributes,
            )
        )
    ordered_tables = sorted(tables, key=lambda value: (value[1][1], value[1][0]))
    if layout_v2:
        placed_tables = []
        for table_index, (rows, box, row_boxes) in enumerate(ordered_tables):
            table_id = f"p{page_number}-t{table_index + 1}"
            if rebuild_merged_tables and _is_merged_column_table(rows):
                lines = _word_rows(page, box)
                header_count = _header_line_count(lines) if table_context else 0
                if header_count > 1:
                    # v5: every row group repeats all printed header lines.
                    lines = ["\n".join(lines[:header_count]), *lines[header_count:]]
                groups, limited = table_row_groups(
                    [[line] for line in lines],
                    "plain_text",
                    table_id=table_id,
                    max_rows=MAX_TABLE_V2_ROWS,
                    max_columns=1,
                    max_cell_characters=None,
                    base_attributes={"origin": "layout", "engine": "pymupdf"},
                    table_fields={"reconstruction": "word-rows"},
                )
                # The rebuilt rows have no row bands; each group spans the table.
                row_boxes = []
            else:
                groups, limited = _table_row_groups(
                    rows,
                    table_mode,
                    table_id=table_id,
                    cell_limit=None
                    if rebuild_merged_tables
                    else MAX_TABLE_V2_CELL_CHARACTERS,
                )
            malformed += int(limited)
            placed_tables.append(
                [
                    CanonicalInputSegment(
                        text=evidence,
                        page_number=page_number,
                        block_type="table",
                        bounding_box=_normalized_box(
                            _group_box(box, row_boxes, first, last), width, height
                        ),
                        attributes=attributes,
                    )
                    for evidence, attributes, first, last in groups
                ]
            )
        return (
            _place_tables(segments, placed_tables),
            len(tables),
            malformed,
            suspicious,
        )
    table_segments = []
    for rows, box, _ in ordered_tables:
        evidence, attributes, truncated = _safe_table(rows, table_mode)
        malformed += int(truncated)
        table_segments.append(
            CanonicalInputSegment(
                text=evidence,
                page_number=page_number,
                block_type="table",
                bounding_box=_normalized_box(box, width, height),
                attributes=attributes,
            )
        )
    # layout-ocr-v1 (frozen): this geometric sort interleaves column blocks.
    segments.extend(table_segments)
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


MAX_OCR_LINE_BOXES = 100


def _ocr_paragraphs(
    rows: list[dict[str, str]],
    *,
    image_width: int,
    image_height: int,
    page_number: int,
    attributes: dict[str, Any],
) -> list[CanonicalInputSegment]:
    """One block per Tesseract paragraph, lines joined in engine reading order."""

    paragraphs: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = {}
    for row in rows:
        paragraph = (row.get("block_num", "0"), row.get("par_num", "0"))
        paragraphs.setdefault(paragraph, {}).setdefault(
            row.get("line_num", "0"), []
        ).append(row)

    def bounds(group: list[dict[str, str]]) -> tuple[int, int, int, int]:
        return (
            min(int(row.get("left") or 0) for row in group),
            min(int(row.get("top") or 0) for row in group),
            max(
                int(row.get("left") or 0) + int(row.get("width") or 0) for row in group
            ),
            max(
                int(row.get("top") or 0) + int(row.get("height") or 0) for row in group
            ),
        )

    segments = []
    for lines in paragraphs.values():
        texts = [
            " ".join((row.get("text") or "").strip() for row in words).strip()
            for words in lines.values()
        ]
        text = "\n".join(value for value in texts if value)
        if not text:
            continue
        words = [row for line in lines.values() for row in line]
        line_boxes = []
        for line in list(lines.values())[:MAX_OCR_LINE_BOXES]:
            box = _normalized_box(bounds(line), image_width, image_height)
            if box is not None:
                line_boxes.append(
                    [
                        round(box.left, 4),
                        round(box.top, 4),
                        round(box.right, 4),
                        round(box.bottom, 4),
                    ]
                )
        segments.append(
            CanonicalInputSegment(
                text=text,
                page_number=page_number,
                block_type="paragraph",
                bounding_box=_normalized_box(bounds(words), image_width, image_height),
                attributes={
                    **attributes,
                    "engine_confidence": round(
                        statistics.mean(float(row.get("conf") or 0) for row in words), 3
                    ),
                    "line_count": len(lines),
                    "line_boxes": line_boxes,
                },
            )
        )
    return segments


def _ocr_page(
    page: pymupdf.Page,
    *,
    page_number: int,
    settings: OcrSettings,
    paragraphs: bool = False,
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
    if paragraphs:
        # layout-ocr-v2 keeps Tesseract's block and paragraph order (plan Slice 4).
        return (
            _ocr_paragraphs(
                [row for group in groups.values() for row in group],
                image_width=image_width,
                image_height=image_height,
                page_number=page_number,
                attributes={
                    "origin": "ocr",
                    "engine": "tesseract",
                    "languages": list(settings.languages),
                    "rotation_applied": rotation,
                    "deskew_degrees": deskew,
                },
            ),
            statistics.median(confidences) if confidences else None,
            rotation,
            deskew,
        )
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


LEGACY_QUALITY_REMEDIATION = (
    "Select Enable robust extraction in the Extract settings to apply the saved "
    "quality policy."
)


def _report_only_quality(
    document: ExtractedDocumentV1, policy, *, duration_ms: int
) -> ExtractedDocumentV1:
    """Measure a native-text-v1 PDF and report findings without changing publication.

    Decision D2 of the Extract plan: legacy versions keep their publication decision,
    so errors are reported as warnings that point to the upgrade.
    """

    decision = document.measurements.quality_decision
    evaluated = evaluate_quality(
        measured_document(document, duration_ms=duration_ms), policy
    )
    findings = [
        finding.model_copy(
            update={
                "severity": "warning"
                if finding.severity == "error"
                else finding.severity,
                "remediation": " ".join(
                    value
                    for value in (finding.remediation, LEGACY_QUALITY_REMEDIATION)
                    if value
                )[:500],
            }
        )
        for finding in evaluated.findings
    ]
    return evaluated.model_copy(
        update={
            "findings": findings,
            "measurements": evaluated.measurements.model_copy(
                update={"quality_decision": decision}
            ),
        }
    )


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
    detected = detect_media_type(path, declared_media_type)
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
        if getattr(settings, "language_policy", None) is not None:
            document = apply_language_policy(document, settings.language_policy)
        return document, NativeTextExtractor.version
    if detected in STRUCTURED_MEDIA_TYPES:
        document, version = extract_structured_document(
            path,
            detected,
            title,
            table_mode=settings.tables
            if settings.config_version in LAYOUT_V2_FAMILY
            else None,
            slide_tables=settings.config_version in V4_READING_VERSIONS,
        )
        document = evaluate_quality(document, settings.quality_policy)
        if getattr(settings, "language_policy", None) is not None:
            document = apply_language_policy(document, settings.language_policy)
        return document, version
    if settings.config_version == "native-text-v1":
        try:
            segments = list(NativeTextExtractor().extract(path, detected))
        except ProcessingError as exc:
            raise IngestionStageError("extract", "extraction_failed", str(exc)) from exc
        page_metadata: dict[int, dict[str, Any]] = {}
        for segment in segments:
            if segment.page_number is None:
                continue
            page = page_metadata.setdefault(
                segment.page_number,
                {"origin": "native", "character_count": 0, "block_count": 0},
            )
            if segment.text:
                page["character_count"] += len(segment.text)
                page["block_count"] += 1
        document = _report_only_quality(
            build_extracted_document(
                segments, media_type=detected, title=title, page_metadata=page_metadata
            ),
            settings.quality_policy,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        if getattr(settings, "language_policy", None) is not None:
            document = apply_language_policy(document, settings.language_policy)
        return document, NativeTextExtractor.version

    # The language list is only needed, and only read, when OCR can run.
    if settings.ocr.mode != "off" and not set(settings.ocr.languages) <= set(
        installed_ocr_languages()
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
    layout_v2 = settings.config_version in LAYOUT_V2_FAMILY
    rebuild_merged_tables = settings.config_version in MERGED_TABLE_VERSIONS
    straighten_sideways = settings.config_version in V4_READING_VERSIONS
    join_soft_hyphens = settings.config_version in V4_READING_VERSIONS
    chart_regions = settings.config_version in CHART_REGION_VERSIONS
    table_context = settings.config_version in TABLE_CONTEXT_VERSIONS
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
                    page,
                    page_number=page_number,
                    settings=settings.ocr,
                    paragraphs=layout_v2,
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
                # v4 reads a sideways page from a straightened copy; its boxes are
                # mapped back to the original page once the layout result is kept.
                text_rotation = (
                    _sideways_rotation(page)
                    if straighten_sideways and rotation == 0
                    else 0
                )
                straight_document = None
                layout_source = page
                if text_rotation:
                    straight_document, layout_source = _straightened_page(
                        page, text_rotation
                    )
                try:
                    layout_segments, page_tables, page_malformed, page_suspicious = (
                        _layout_page(
                            layout_source,
                            page_number=page_number,
                            table_mode=settings.tables,
                            layout_v2=layout_v2,
                            rebuild_merged_tables=rebuild_merged_tables,
                            chart_regions=chart_regions,
                            table_context=table_context,
                        )
                    )
                finally:
                    if straight_document is not None:
                        straight_document.close()
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
                if settings.strategy == "auto" and layout_v2:
                    # v2 keeps structure unless layout analysis lost text. Columns need
                    # narrow blocks on both halves, so short headings and indented
                    # list items on a single-column page do not count.
                    narrow = [
                        item.bounding_box
                        for item in layout_segments
                        if item.bounding_box
                        and item.bounding_box.right - item.bounding_box.left < 0.62
                    ]
                    two_columns = (
                        sum(box.right <= 0.55 for box in narrow) >= 2
                        and sum(box.left >= 0.45 for box in narrow) >= 2
                    )
                    if page_tables:
                        use_layout, reason = True, "table_detected"
                    elif two_columns:
                        use_layout, reason = True, "multiple_columns_detected"
                    elif layout_characters < native_characters * LAYOUT_TEXT_LOSS_RATIO:
                        use_layout, reason = False, None
                        fallback_reason = "layout_text_loss"
                    else:
                        use_layout, reason = True, "layout_structure"
                elif settings.strategy == "auto":
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
                    if text_rotation:
                        page_segments = [
                            replace(
                                item,
                                bounding_box=_unrotated_box(
                                    item.bounding_box, text_rotation
                                ),
                            )
                            for item in layout_segments
                        ]
                        rotation = text_rotation
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
            if join_soft_hyphens:
                page_segments = [
                    replace(item, text=_SOFT_HYPHEN_BREAK.sub("", item.text))
                    if item.block_type != "table"
                    else item
                    for item in page_segments
                ]
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
    if layout_v2:
        segments = _heading_structure(segments)
    if table_context:
        segments = _table_captions(segments)
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
    document = evaluate_quality(document, settings.quality_policy)
    if getattr(settings, "language_policy", None) is not None:
        document = apply_language_policy(document, settings.language_policy)
    return document, extractor_version_for_settings(settings)


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
