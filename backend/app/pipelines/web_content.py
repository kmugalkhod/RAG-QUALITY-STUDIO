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
    block_type: str = "paragraph"
    attributes: dict | None = None


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


_SEMANTIC_ROLE = {
    "main": "main",
    "nav": "navigation",
    "header": "banner",
    "footer": "contentinfo",
    "aside": "complementary",
    "dialog": "dialog",
    "form": "form",
}
_STRUCTURED_BLOCKS = {
    "p": "paragraph",
    "li": "list_item",
    "pre": "code",
    "blockquote": "quote",
    "td": "table",
    "th": "table",
    "figcaption": "image_caption",
    "footer": "footnote",
    "div": "unknown",
    "section": "unknown",
    "nav": "unknown",
    "header": "unknown",
    "aside": "unknown",
    "dialog": "unknown",
    "form": "unknown",
}


class _StructuredContent(HTMLParser):
    """Bounded semantic HTML reader; CSS and script content are never evaluated."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.stack: list[tuple[str, tuple[str, ...], str | None, bool]] = []
        self.headings: list[str] = []
        self.heading_level: int | None = None
        self.heading_parts: list[str] = []
        self.buffer: list[str] = []
        self.current_tag = "p"
        self.current_selectors: tuple[str, ...] = ()
        self.current_role: str | None = None
        self.current_main = False
        self.sections: list[Section] = []

    @staticmethod
    def _tokens(tag: str, attrs) -> tuple[tuple[str, ...], str | None]:
        values = {
            str(key).lower(): str(value) for key, value in attrs if value is not None
        }
        tokens = [tag]
        element_id = values.get("id")
        if element_id and re.fullmatch(r"[a-zA-Z0-9_-]+", element_id):
            tokens.append(f"#{element_id}")
        for value in values.get("class", "").split()[:20]:
            if re.fullmatch(r"[a-zA-Z0-9_-]+", value):
                tokens.append(f".{value}")
        role = values.get("role") or _SEMANTIC_ROLE.get(tag)
        if role in {
            "main",
            "navigation",
            "banner",
            "contentinfo",
            "complementary",
            "dialog",
            "form",
        }:
            tokens.append(f"[role={role}]")
        else:
            role = None
        return tuple(tokens), role

    def _context(self, tag: str, attrs):
        own, role = self._tokens(tag, attrs)
        inherited = [token for _, tokens, _, _ in self.stack for token in tokens]
        selectors = tuple(dict.fromkeys((inherited + list(own))[:50]))
        main = tag == "main" or role == "main" or any(item[3] for item in self.stack)
        semantic_role = role or next(
            (item[2] for item in reversed(self.stack) if item[2]), None
        )
        return selectors, semantic_role, main

    def flush(self):
        value = "".join(self.buffer)
        if value.strip():
            value = value.strip()
            self.sections.append(
                Section(
                    path=tuple(self.headings),
                    text=value,
                    block_type=_STRUCTURED_BLOCKS.get(self.current_tag, "paragraph"),
                    attributes={
                        "html_tag": self.current_tag,
                        "html_role": self.current_role,
                        "html_main": self.current_main,
                        "html_selectors": list(self.current_selectors),
                    },
                )
            )
        self.buffer.clear()

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template", "svg"}:
            self.ignored += 1
            return
        if self.ignored:
            return
        selectors, role, main = self._context(tag, attrs)
        if tag in _STRUCTURED_BLOCKS or (
            len(tag) == 2 and tag[0] == "h" and tag[1].isdigit()
        ):
            self.flush()
            self.current_tag = tag
            self.current_selectors = selectors
            self.current_role = role
            self.current_main = main
        self.stack.append((tag, selectors, role, main))
        if len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
            self.heading_level = int(tag[1])
            self.heading_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template", "svg"}:
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
                self.sections.append(
                    Section(
                        path=tuple(self.headings[:-1]),
                        text=value,
                        block_type="heading",
                        attributes={
                            "html_tag": tag,
                            "html_role": self.current_role,
                            "html_main": self.current_main,
                            "html_selectors": list(self.current_selectors),
                        },
                    )
                )
            self.heading_level = None
            self.heading_parts = []
            self.buffer.clear()
        elif tag in _STRUCTURED_BLOCKS:
            self.flush()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.ignored:
            return
        if self.heading_level is not None:
            self.heading_parts.append(data)
        else:
            self.buffer.append(data)


def extract_canonical_sections(content: bytes) -> list[Section]:
    """Extract structured, selector-aware blocks without executing source content."""

    parser = _StructuredContent()
    parser.feed(content.decode("utf-8", errors="replace"))
    parser.flush()
    return parser.sections[:100_000]


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
