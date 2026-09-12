"""Deterministic, non-executing HTML extraction and section-local chunking."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from app.pipelines.parsing import MAX_CHUNKS, ProcessingError, windows


EXTRACTOR_VERSION = "html-main-v1"
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
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.main_depth = 0
        self.heading_level: int | None = None
        self.heading_parts: list[str] = []
        self.headings: list[str] = []
        self.entries: list[tuple[bool, tuple[str, ...], str]] = []
        self.buffer: list[str] = []

    def flush(self):
        value = _SPACE.sub(" ", " ".join(self.buffer)).strip()
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


def extract_sections(content: bytes, clean) -> list[Section]:
    parser = _Content()
    parser.feed(content.decode("utf-8", errors="replace"))
    parser.flush()
    entries = parser.entries
    main = [entry for entry in entries if entry[0]]
    if main:
        entries = main
    boilerplate = tuple(value.strip() for value in clean.repeated_boilerplate)
    sections = []
    for _, path, value in entries:
        if clean.normalize_whitespace:
            value = _SPACE.sub(" ", value).strip()
        for repeated in boilerplate:
            value = value.replace(repeated, " ")
        value = _SPACE.sub(" ", value).strip()
        if value:
            sections.append(Section(path=path, text=value))
    combined = "\n\n".join(section.text for section in sections)
    if len(combined) < clean.minimum_text_chars:
        raise ProcessingError("Website page contains too little extractable main text.")
    if len(combined) > clean.maximum_text_chars:
        raise ProcessingError("Website page exceeds the configured cleaned-text limit.")
    return sections


def chunk_sections(sections: list[Section], size: int, overlap: int):
    chunks = []
    cursor = 0
    for section in sections:
        for start, end, text in windows(section.text, size, overlap):
            if len(chunks) >= MAX_CHUNKS:
                raise ProcessingError(
                    "Website page exceeds the 50,000 chunk limit. Increase chunk size."
                )
            chunks.append(
                {
                    "ordinal": len(chunks),
                    "page_number": None,
                    "start_char": cursor + start,
                    "end_char": cursor + end,
                    "text": text,
                    "provenance": {"section_path": list(section.path)},
                }
            )
        cursor += len(section.text) + 2
    if not chunks:
        raise ProcessingError("Website page contains no chunkable text.")
    return chunks
