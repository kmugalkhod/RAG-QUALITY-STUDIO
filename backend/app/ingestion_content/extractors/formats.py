"""Bounded structured-file adapters for the explicitly released Phase 7B formats."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from app.ingestion_content.canonical import (
    CanonicalInputSegment,
    build_extracted_document,
)
from app.ingestion_content.processing import IngestionStageError
from app.ingestion_content.quality import measured_document
from app.pipelines.parsing import MAX_CHARACTERS, ProcessingError, validate_text


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MARKDOWN = "text/markdown"
HTML = "text/html"
CSV = "text/csv"
TSV = "text/tab-separated-values"
STRUCTURED_MEDIA_TYPES = {DOCX, PPTX, XLSX, MARKDOWN, HTML, CSV, TSV}
FORMAT_EXTRACTOR_VERSION = "formats-v1"

MAX_ARCHIVE_MEMBERS = 5_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 10 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_TABULAR_ROWS = 100_000
MAX_TABULAR_COLUMNS = 1_000
MAX_TABULAR_CELLS = 1_000_000


def _safe_archive(path: Path) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path)
        members = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise IngestionStageError(
            "extract", "malformed_package", "The packaged document is malformed."
        ) from exc
    if not members or len(members) > MAX_ARCHIVE_MEMBERS:
        archive.close()
        raise IngestionStageError(
            "extract",
            "archive_member_limit",
            "The packaged document exceeds its member limit.",
        )
    total = 0
    names: set[str] = set()
    for member in members:
        parts = PurePosixPath(member.filename).parts
        total += member.file_size
        ratio = member.file_size / max(member.compress_size, 1)
        file_kind = (member.external_attr >> 16) & 0o170000
        if member.filename.lower().endswith("vbaproject.bin"):
            archive.close()
            raise IngestionStageError(
                "extract",
                "macro_package_unsupported",
                "Macro-enabled Office packages are unsupported.",
            )
        if (
            member.flag_bits & 0x1
            or member.filename in names
            or member.file_size > MAX_ARCHIVE_MEMBER_BYTES
            or total > MAX_ARCHIVE_UNCOMPRESSED_BYTES
            or ratio > MAX_COMPRESSION_RATIO
            or file_kind == 0o120000
            or member.filename.startswith("/")
            or ".." in parts
        ):
            archive.close()
            raise IngestionStageError(
                "extract",
                "unsafe_package",
                "The packaged document violates encrypted, path, size or compression limits.",
            )
        names.add(member.filename)
    return archive


def detect_structured_media_type(
    path: Path, declared_media_type: str | None
) -> str | None:
    with path.open("rb") as source:
        prefix = source.read(8192)
    if prefix.startswith(b"PK\x03\x04"):
        with _safe_archive(path) as archive:
            names = set(archive.namelist())
            if "word/document.xml" in names:
                return DOCX
            if "ppt/presentation.xml" in names and any(
                name.startswith("ppt/slides/slide") for name in names
            ):
                return PPTX
            if "xl/workbook.xml" in names and any(
                name.startswith("xl/worksheets/sheet") for name in names
            ):
                return XLSX
        raise IngestionStageError(
            "extract",
            "unsupported_package",
            "The ZIP package is not a supported DOCX, PPTX or XLSX document.",
        )
    if prefix.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise IngestionStageError(
            "extract",
            "legacy_office_unsupported",
            "Legacy binary Office files are unsupported; save as DOCX, PPTX or XLSX.",
        )
    if declared_media_type not in {MARKDOWN, HTML, CSV, TSV}:
        return None
    try:
        validate_text(path.read_bytes())
    except ProcessingError as exc:
        raise IngestionStageError(
            "extract", "invalid_utf8", "The text-based document must be valid UTF-8."
        ) from exc
    text = path.read_text("utf-8")
    looks_html = re.search(
        r"<\s*(?:!doctype\s+html|html|head|body|p|h[1-6]|table)\b", text, re.I
    )
    if declared_media_type == HTML and not looks_html:
        raise IngestionStageError(
            "extract",
            "media_type_mismatch",
            "The HTML filename does not contain HTML content.",
        )
    if declared_media_type == MARKDOWN and looks_html:
        raise IngestionStageError(
            "extract",
            "media_type_mismatch",
            "The Markdown filename contains HTML content.",
        )
    return declared_media_type


def _bounded_text(value: str) -> str:
    value = value.replace("\x00", "").strip()
    if len(value) > MAX_CHARACTERS:
        raise IngestionStageError(
            "extract",
            "character_limit",
            "Document exceeds the character processing limit.",
        )
    return value


def _markdown_segments(text: str) -> list[CanonicalInputSegment]:
    segments: list[CanonicalInputSegment] = []
    headings: list[str] = []
    paragraph: list[str] = []
    code: list[str] = []
    fenced = False

    def flush_paragraph():
        if paragraph:
            segments.append(
                CanonicalInputSegment(
                    text=" ".join(paragraph),
                    block_type="paragraph",
                    heading_path=tuple(headings),
                )
            )
            paragraph.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            flush_paragraph()
            if fenced:
                if code:
                    segments.append(
                        CanonicalInputSegment(
                            text="\n".join(code),
                            block_type="code",
                            heading_path=tuple(headings),
                        )
                    )
                    code.clear()
                fenced = False
            else:
                fenced = True
            continue
        if fenced:
            code.append(line)
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            label = heading.group(2).strip()
            headings[:] = headings[: level - 1]
            headings.append(label)
            segments.append(
                CanonicalInputSegment(
                    text=label, block_type="heading", heading_path=tuple(headings[:-1])
                )
            )
            continue
        listed = re.match(r"^\s*(?:[-+*]|\d+[.)])\s+(.+)$", line)
        if listed:
            flush_paragraph()
            segments.append(
                CanonicalInputSegment(
                    text=listed.group(1).strip(),
                    block_type="list_item",
                    heading_path=tuple(headings),
                )
            )
        elif line.lstrip().startswith(">"):
            flush_paragraph()
            segments.append(
                CanonicalInputSegment(
                    text=line.lstrip()[1:].strip(),
                    block_type="quote",
                    heading_path=tuple(headings),
                )
            )
        elif not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line.strip())
    flush_paragraph()
    if code:
        segments.append(
            CanonicalInputSegment(
                text="\n".join(code), block_type="code", heading_path=tuple(headings)
            )
        )
    return segments


class _HTMLBlocks(HTMLParser):
    ignored = {"script", "style", "noscript", "template", "svg"}
    block_types = {
        "title": "title",
        "p": "paragraph",
        "li": "list_item",
        "pre": "code",
        "blockquote": "quote",
        "figcaption": "image_caption",
        "table": "table",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current: tuple[str, int] | None = None
        self.buffer: list[str] = []
        self.headings: list[str] = []
        self.segments: list[CanonicalInputSegment] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in self.ignored:
            self.depth += 1
            return
        if self.depth:
            return
        if tag == "br":
            self.buffer.append("\n")
        if re.fullmatch(r"h[1-6]", tag):
            self._finish()
            self.current = ("heading", int(tag[1]))
        elif tag in self.block_types:
            self._finish()
            self.current = (self.block_types[tag], 0)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self.ignored:
            self.depth = max(0, self.depth - 1)
            return
        if not self.depth and (re.fullmatch(r"h[1-6]", tag) or tag in self.block_types):
            self._finish()

    def handle_data(self, data: str):
        if not self.depth and data.strip():
            self.buffer.append(data)

    def _finish(self):
        text = re.sub(r"[ \t\r\f\v]+", " ", "".join(self.buffer)).strip()
        self.buffer.clear()
        if not text:
            self.current = None
            return
        kind, level = self.current or ("paragraph", 0)
        if kind == "heading":
            self.headings[:] = self.headings[: level - 1]
            path = tuple(self.headings)
            self.headings.append(text)
        else:
            path = tuple(self.headings)
        self.segments.append(
            CanonicalInputSegment(text=text, block_type=kind, heading_path=path)
        )
        self.current = None


def _html_segments(text: str) -> list[CanonicalInputSegment]:
    parser = _HTMLBlocks()
    try:
        parser.feed(text)
        parser.close()
        parser._finish()
    except Exception as exc:
        raise IngestionStageError(
            "extract", "malformed_html", "The HTML document could not be parsed."
        ) from exc
    return parser.segments


def _tabular_segments(
    text: str, delimiter: str, label: str
) -> list[CanonicalInputSegment]:
    csv.field_size_limit(100_000)
    try:
        rows = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
        result = []
        width = None
        cells = 0
        for index, row in enumerate(rows):
            if index >= MAX_TABULAR_ROWS or len(row) > MAX_TABULAR_COLUMNS:
                raise IngestionStageError(
                    "extract",
                    "table_limit",
                    "The tabular document exceeds row or column limits.",
                )
            width = len(row) if width is None else width
            if len(row) != width:
                raise IngestionStageError(
                    "extract",
                    "malformed_table",
                    "The tabular document has inconsistent columns.",
                )
            cells += len(row)
            if cells > MAX_TABULAR_CELLS:
                raise IngestionStageError(
                    "extract",
                    "table_limit",
                    "The tabular document exceeds its cell limit.",
                )
            escaped = [value.replace("|", "\\|").strip() for value in row]
            result.append(
                CanonicalInputSegment(
                    text="| " + " | ".join(escaped) + " |",
                    block_type="table",
                    attributes={"table": label, "row": index + 1, "header": index == 0},
                )
            )
        return result
    except (csv.Error, UnicodeError) as exc:
        raise IngestionStageError(
            "extract", "malformed_table", "The tabular document could not be parsed."
        ) from exc


def _xml(archive: zipfile.ZipFile, name: str):
    try:
        return ElementTree.fromstring(archive.read(name))
    except (KeyError, ElementTree.ParseError, OSError) as exc:
        raise IngestionStageError(
            "extract", "malformed_package", "The packaged document XML is malformed."
        ) from exc


def _texts(element) -> list[str]:
    return [value.text or "" for value in element.findall(".//{*}t")]


def _docx_segments(archive: zipfile.ZipFile) -> list[CanonicalInputSegment]:
    if any(name.lower().endswith("vbaproject.bin") for name in archive.namelist()):
        raise IngestionStageError(
            "extract",
            "macro_package_unsupported",
            "Macro-enabled Office packages are unsupported.",
        )
    root = _xml(archive, "word/document.xml")
    body = root.find(".//{*}body")
    result: list[CanonicalInputSegment] = []
    headings: list[str] = []
    for child in list(body) if body is not None else []:
        if child.tag.endswith("}p"):
            value = "".join(_texts(child)).strip()
            if not value:
                continue
            style = child.find(".//{*}pStyle")
            style_name = (
                next(iter(style.attrib.values()), "") if style is not None else ""
            )
            match = re.match(r"Heading(\d)", style_name, re.I)
            if match:
                level = int(match.group(1))
                headings[:] = headings[: level - 1]
                path = tuple(headings)
                headings.append(value)
                kind = "heading"
            else:
                path = tuple(headings)
                kind = (
                    "list_item"
                    if child.find(".//{*}numPr") is not None
                    else "paragraph"
                )
            result.append(
                CanonicalInputSegment(value, block_type=kind, heading_path=path)
            )
        elif child.tag.endswith("}tbl"):
            for row_index, row in enumerate(child.findall(".//{*}tr")):
                cells = [
                    "".join(_texts(cell)).strip() for cell in row.findall("./{*}tc")
                ]
                result.append(
                    CanonicalInputSegment(
                        "| " + " | ".join(cells) + " |",
                        block_type="table",
                        heading_path=tuple(headings),
                        attributes={"row": row_index + 1},
                    )
                )
    return result


def _pptx_segments(archive: zipfile.ZipFile) -> list[CanonicalInputSegment]:
    names = sorted(
        (
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ),
        key=lambda value: int(re.search(r"(\d+)", value.rsplit("/", 1)[-1]).group(1)),
    )
    result = []
    for page_number, name in enumerate(names, 1):
        root = _xml(archive, name)
        for shape_index, shape in enumerate(root.findall(".//{*}sp")):
            paragraphs = []
            for paragraph in shape.findall(".//{*}p"):
                value = "".join(_texts(paragraph)).strip()
                if value:
                    paragraphs.append(value)
            if paragraphs:
                result.append(
                    CanonicalInputSegment(
                        "\n".join(paragraphs),
                        page_number=page_number,
                        block_type="paragraph",
                        attributes={"slide": page_number, "shape": shape_index + 1},
                    )
                )
    return result


def _xlsx_segments(archive: zipfile.ZipFile) -> list[CanonicalInputSegment]:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        shared = [
            "".join(_texts(item))
            for item in _xml(archive, "xl/sharedStrings.xml").findall(".//{*}si")
        ]
    names = sorted(
        (
            name
            for name in archive.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        ),
        key=lambda value: int(re.search(r"(\d+)", value.rsplit("/", 1)[-1]).group(1)),
    )
    result = []
    cells = 0
    rows = 0
    for sheet_number, name in enumerate(names, 1):
        root = _xml(archive, name)
        for row in root.findall(".//{*}row"):
            rows += 1
            values = []
            for cell in row.findall("./{*}c"):
                cells += 1
                if rows > MAX_TABULAR_ROWS or cells > MAX_TABULAR_CELLS:
                    raise IngestionStageError(
                        "extract",
                        "table_limit",
                        "The workbook exceeds row or cell limits.",
                    )
                kind = cell.attrib.get("t")
                raw = cell.findtext("./{*}v", default="")
                if kind == "s" and raw.isdigit() and int(raw) < len(shared):
                    value = shared[int(raw)]
                elif kind == "inlineStr":
                    value = "".join(_texts(cell))
                else:
                    value = raw
                formula = cell.findtext("./{*}f")
                values.append(f"={formula}" if formula else value)
            if len(values) > MAX_TABULAR_COLUMNS:
                raise IngestionStageError(
                    "extract", "table_limit", "The workbook exceeds its column limit."
                )
            if values:
                result.append(
                    CanonicalInputSegment(
                        "| "
                        + " | ".join(value.replace("|", "\\|") for value in values)
                        + " |",
                        page_number=sheet_number,
                        block_type="table",
                        attributes={"sheet": sheet_number, "row": rows},
                    )
                )
    return result


def extract_structured_document(path: Path, media_type: str, title: str | None):
    if media_type in {MARKDOWN, HTML, CSV, TSV}:
        text = _bounded_text(path.read_text("utf-8"))
        if media_type == MARKDOWN:
            segments = _markdown_segments(text)
        elif media_type == HTML:
            segments = _html_segments(text)
        else:
            segments = _tabular_segments(
                text, "," if media_type == CSV else "\t", title or "table"
            )
    else:
        with _safe_archive(path) as archive:
            if media_type == DOCX:
                segments = _docx_segments(archive)
            elif media_type == PPTX:
                segments = _pptx_segments(archive)
            elif media_type == XLSX:
                segments = _xlsx_segments(archive)
            else:
                raise IngestionStageError(
                    "extract",
                    "unsupported_media_type",
                    "The document format is unsupported.",
                )
    total = sum(len(segment.text) for segment in segments)
    if not segments or total > MAX_CHARACTERS:
        raise IngestionStageError(
            "extract",
            "no_useful_text" if not segments else "character_limit",
            "The document has no useful text or exceeds the character limit.",
        )
    page_metadata = {
        page: {
            "origin": "native",
            "character_count": sum(
                len(segment.text) for segment in segments if segment.page_number == page
            ),
            "block_count": sum(segment.page_number == page for segment in segments),
        }
        for page in sorted(
            {
                segment.page_number
                for segment in segments
                if segment.page_number is not None
            }
        )
    }
    document = build_extracted_document(
        segments, media_type=media_type, title=title, page_metadata=page_metadata
    )
    return (
        measured_document(
            document,
            duration_ms=0,
            table_count=sum(segment.block_type == "table" for segment in segments),
        ),
        FORMAT_EXTRACTOR_VERSION,
    )
