"""Deterministic, non-executing HTML extraction and page-window chunking."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from app.ingestion_content import (
    CharacterWindowChunker,
    ExtractedSegment,
    cleaner_for_node,
)
from app.pipelines.parsing import MAX_CHUNKS, ProcessingError


EXTRACTOR_VERSION = "html-main-v2"
CLEANER_VERSION = "whitespace-boilerplate-v1"
_SPACE = re.compile(r"\s+")
_IGNORED = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "nav",
    "header",
    "footer",
    "form",
}
_BLOCKS = {"p", "li", "pre", "blockquote", "td", "th", "div", "section", "br"}


@dataclass(frozen=True)
class Section:
    path: tuple[str, ...]
    text: str


class _Content(HTMLParser):
    def __init__(self, preserve_whitespace: bool = False):
        super().__init__(convert_charrefs=True)
        self.preserve_whitespace = preserve_whitespace
        self.ignored = 0
        self.main_depth = 0
        self.heading_level: int | None = None
        self.heading_parts: list[str] = []
        self.headings: list[str] = []
        self.entries: list[tuple[bool, tuple[str, ...], str]] = []
        self.buffer: list[str] = []

    def flush(self):
        raw = (
            "".join(self.buffer) if self.preserve_whitespace else " ".join(self.buffer)
        )
        value = raw if self.preserve_whitespace else _SPACE.sub(" ", raw).strip()
        if value:
            self.entries.append((self.main_depth > 0, tuple(self.headings), value))
        self.buffer.clear()

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _IGNORED:
            self.flush()
            self.ignored += 1
            return
        if self.ignored:
            return
        if tag in ("main", "article"):
            self.flush()
            self.main_depth += 1
        if len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
            self.flush()
            self.heading_level = int(tag[1])
            self.heading_parts = []
        elif tag in _BLOCKS:
            self.flush()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _IGNORED:
            if self.ignored:
                self.ignored -= 1
            return
        if self.ignored:
            return
        if self.heading_level is not None and tag == f"h{self.heading_level}":
            value = _SPACE.sub(" ", " ".join(self.heading_parts)).strip()
            if value:
                self.headings = self.headings[: self.heading_level - 1]
                self.headings.append(value[:500])
            self.heading_level = None
            self.heading_parts = []
        elif tag in _BLOCKS:
            self.flush()
        if tag in ("main", "article") and self.main_depth:
            self.flush()
            self.main_depth -= 1

    def handle_data(self, data):
        if self.ignored:
            return
        if self.heading_level is not None:
            self.heading_parts.append(data)
        else:
            self.buffer.append(data)


def extract_sections(content: bytes, clean, phase_callback=None) -> list[Section]:
    standard = getattr(clean, "profile", None) == "standard-v1"
    sections = extract_raw_sections(
        content, preserve_whitespace=standard and not clean.normalize_whitespace
    )
    if phase_callback is not None:
        phase_callback("clean")
    cleaner = cleaner_for_node(clean)
    sections = [
        Section(path=section.path, text=value)
        for section in sections
        if (value := cleaner.clean(section.text, clean))
    ]
    combined = "\n\n".join(section.text for section in sections)
    length_violation = cleaner.length_violation(len(combined), clean)
    if length_violation == "too_short":
        raise ProcessingError("Website page contains too little extractable main text.")
    if length_violation == "too_long":
        raise ProcessingError("Website page exceeds the configured cleaned-text limit.")
    return sections


def extract_raw_sections(
    content: bytes, *, preserve_whitespace: bool = False
) -> list[Section]:
    """Extract safe HTML text boundaries without applying cleaning semantics."""

    parser = _Content(preserve_whitespace=preserve_whitespace)
    parser.feed(content.decode("utf-8", errors="replace"))
    parser.flush()
    entries = parser.entries
    main = [entry for entry in entries if entry[0]]
    if main:
        entries = main
    return [Section(path=path, text=value) for _, path, value in entries]


def chunk_sections(sections: list[Section], size: int, overlap: int):
    """Chunk one cleaned page while retaining the shared heading provenance.

    HTML elements are extraction boundaries, not semantic chunk boundaries. Joining
    adjacent elements before windowing prevents headings, list items and short
    paragraphs from becoming useless one-line vectors.
    """
    combined = "\n\n".join(section.text for section in sections)
    spans = []
    cursor = 0
    for section in sections:
        end = cursor + len(section.text)
        spans.append((cursor, end, section.path))
        cursor = end + 2

    def shared_path(start: int, end: int) -> list[str]:
        paths = [path for left, right, path in spans if left < end and right > start]
        if not paths:
            return []
        prefix = list(paths[0])
        for path in paths[1:]:
            prefix = [
                value
                for index, value in enumerate(prefix)
                if index < len(path) and path[index] == value
            ]
            if not prefix:
                break
        return prefix

    chunks = []
    chunker = CharacterWindowChunker()
    settings = type("Settings", (), {"size": size, "overlap": overlap})()
    for prepared in chunker.chunk_segment(ExtractedSegment(text=combined), settings):
        if len(chunks) >= MAX_CHUNKS:
            raise ProcessingError(
                "Website page exceeds the 50,000 chunk limit. Increase chunk size."
            )
        value = prepared.as_record()
        value["provenance"] = {
            "section_path": shared_path(prepared.start_char, prepared.end_char)
        }
        chunks.append(value)
    if not chunks:
        raise ProcessingError("Website page contains no chunkable text.")
    return chunks
