"""Deterministic structure-aware and parent/child chunk construction."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, replace
from typing import Any, Iterable

from app.ingestion_content.contracts import (
    CanonicalBlock,
    ChunkBlockSpanV1,
    CleanedDocumentV1,
)
from app.ingestion_content.processing import PreparedChunk
from app.ingestion_content.tokenizers import Utf8ByteTokenizer, tokenizer_for


_BOUNDARY = re.compile(r"(?:\n{2,}|(?<=[.!?])\s+|\n)")
# v3 also ends sentences after the full-width "。！？", which have no space after them.
_BOUNDARY_V3 = re.compile(r"(?:\n{2,}|(?<=[.!?])\s+|(?<=[。！？])|\n)")
_SPACE_RUN = re.compile(r"\s+")
# Where a v3 overlap may start: after whitespace or a full-width sentence end.
_WORD_START_V3 = re.compile(r"\s+|(?<=[。！？])")
_MARKDOWN_DIVIDER = re.compile(r"^\s*\|?\s*:?-{3,}")
_PROTECTED = {"list_item", "table", "code"}
# Spec 0012 Part D: v3 starts overlap and hard splits at a sentence or word
# boundary, joins a remainder under 40 bytes to its neighbour, and does not repeat
# a heading that already starts the passage in its prefix. v1 and v2 are frozen.
V3_VERSIONS = {"section-token-v3", "parent-child-v3"}
# Versions that append a section's short first chunk to the chunk before it on the
# same page (spec 0010). A chart callout or label read as a heading otherwise stands
# alone as a chunk of a few words that no question ranks first.
SHORT_CHUNK_MERGE_VERSIONS = {"section-token-v2", "parent-child-v2", *V3_VERSIONS}
SHORT_CHUNK_TOKENS = 40
# The embedding adapter's per-input limit in UTF-8 bytes, and the most the
# "Section: …" heading prefix may add to a passage (spec 0012 D5).
EMBEDDING_INPUT_BYTES = 8191
HEADING_PREFIX_BYTES = 300


@dataclass(frozen=True)
class _Mapping:
    block: CanonicalBlock
    block_start: int
    block_end: int
    piece_start: int
    piece_end: int


@dataclass(frozen=True)
class _Piece:
    text: str
    mappings: tuple[_Mapping, ...]
    section_path: tuple[str, ...]
    page_number: int | None
    protected: bool
    findings: tuple[dict[str, Any], ...] = ()


def _section_path(block: CanonicalBlock) -> tuple[str, ...]:
    if block.type == "heading":
        return (*block.heading_path, block.text[:500])
    return tuple(block.heading_path)


def _piece(block: CanonicalBlock, ranges: Iterable[tuple[int, int]], findings=()):
    text_parts: list[str] = []
    mappings: list[_Mapping] = []
    cursor = 0
    for start, end in ranges:
        value = block.text[start:end]
        if not value:
            continue
        text_parts.append(value)
        mappings.append(
            _Mapping(
                block=block,
                block_start=start,
                block_end=end,
                piece_start=cursor,
                piece_end=cursor + len(value),
            )
        )
        cursor += len(value)
    return _Piece(
        text="".join(text_parts),
        mappings=tuple(mappings),
        section_path=_section_path(block),
        page_number=block.page_number,
        protected=block.type in _PROTECTED,
        findings=tuple(findings),
    )


def _split_ranges(
    text: str, maximum_tokens: int, tokenizer: Utf8ByteTokenizer, v3: bool = False
) -> list[tuple[int, int]]:
    """Split a block into ranges of at most `maximum_tokens`, preferring to end at a
    sentence or line boundary. Spec 0012 C1: byte offsets are computed once and both
    the budget end and the last boundary are found by bisection, so a long block is
    split in linear time with exactly the ranges of the original scan."""
    boundaries = [
        match.end() for match in (_BOUNDARY_V3 if v3 else _BOUNDARY).finditer(text)
    ]
    # v3 falls back to the end of a whitespace run before cutting inside a word.
    spaces = [match.end() for match in _SPACE_RUN.finditer(text)] if v3 else []
    offsets = tokenizer.byte_offsets(text)
    ranges: list[tuple[int, int]] = []
    start = 0
    length = len(text)
    while start < length:
        # The largest end whose bytes since `start` fit the budget (prefix_end).
        cap = bisect_right(offsets, offsets[start] + maximum_tokens) - 1
        if cap == length:
            ranges.append((start, cap))
            break
        if cap <= start:
            cap = start + 1
        last = bisect_right(boundaries, cap) - 1
        preferred = boundaries[last] if last >= 0 and boundaries[last] > start else cap
        if v3 and preferred == cap:
            space = bisect_right(spaces, cap) - 1
            if space >= 0 and spaces[space] > start:
                preferred = spaces[space]
        ranges.append((start, preferred))
        start = preferred
    if v3:
        ranges = _rebalance_remainder(
            ranges, offsets, boundaries, spaces, maximum_tokens
        )
    return ranges


def _rebalance_remainder(ranges, offsets, boundaries, spaces, maximum_tokens):
    """v3: a final range under 40 bytes joins the range before it, or, when both
    would not fit, takes text from it at a boundary so neither is that short."""
    if len(ranges) < 2:
        return ranges
    (previous_start, split), (_, end) = ranges[-2], ranges[-1]
    if offsets[end] - offsets[split] >= SHORT_CHUNK_TOKENS:
        return ranges
    if offsets[end] - offsets[previous_start] <= maximum_tokens:
        return [*ranges[:-2], (previous_start, end)]
    candidates = sorted({*boundaries, *spaces}, reverse=True)
    for point in candidates:
        if not previous_start < point < split:
            continue
        tail = offsets[end] - offsets[point]
        if tail > maximum_tokens:
            break
        if tail >= SHORT_CHUNK_TOKENS:
            return [*ranges[:-2], (previous_start, point), (point, end)]
    return ranges


def _line_ranges(text: str) -> list[tuple[int, int]]:
    ranges = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        ranges.append((cursor, cursor + len(line)))
        cursor += len(line)
    if cursor < len(text):
        ranges.append((cursor, len(text)))
    return ranges or [(0, len(text))]


def _table_pieces(
    block: CanonicalBlock,
    maximum_tokens: int,
    tokenizer: Utf8ByteTokenizer,
    v3: bool = False,
) -> list[_Piece]:
    if tokenizer.count(block.text) <= maximum_tokens:
        return [_piece(block, [(0, len(block.text))])]
    lines = _line_ranges(block.text)
    header_count = (
        2
        if len(lines) > 1 and _MARKDOWN_DIVIDER.match(block.text[slice(*lines[1])])
        else 1
    )
    headers = lines[:header_count]
    body = lines[header_count:]
    header_tokens = tokenizer.count(
        "".join(block.text[start:end] for start, end in headers)
    )
    if not body or header_tokens >= maximum_tokens:
        return [
            _piece(
                block,
                [value],
                findings=(
                    {
                        "code": "oversize_table_split",
                        "message": "A table exceeded the hard token limit and was split at a Unicode boundary.",
                    },
                ),
            )
            for value in _split_ranges(block.text, maximum_tokens, tokenizer, v3)
        ]

    result: list[_Piece] = []
    rows: list[tuple[int, int]] = []
    for row in body:
        row_text = block.text[slice(*row)]
        if tokenizer.count(row_text) + header_tokens > maximum_tokens:
            if rows:
                result.append(_piece(block, [*headers, *rows]))
                rows = []
            for part in _split_ranges(
                row_text, maximum_tokens - header_tokens, tokenizer, v3
            ):
                result.append(
                    _piece(
                        block,
                        [*headers, (row[0] + part[0], row[0] + part[1])],
                        findings=(
                            {
                                "code": "oversize_table_row_split",
                                "message": "A table row exceeded the hard token limit and was split at a Unicode boundary.",
                            },
                        ),
                    )
                )
            continue
        candidate = [*headers, *rows, row]
        if (
            rows
            and tokenizer.count(
                "".join(block.text[start:end] for start, end in candidate)
            )
            > maximum_tokens
        ):
            result.append(_piece(block, [*headers, *rows]))
            rows = [row]
        else:
            rows.append(row)
    if rows:
        result.append(_piece(block, [*headers, *rows]))
    return result


def _block_pieces(
    block: CanonicalBlock,
    maximum_tokens: int,
    tokenizer: Utf8ByteTokenizer,
    v3: bool = False,
) -> list[_Piece]:
    if block.type == "table":
        return _table_pieces(block, maximum_tokens, tokenizer, v3)
    if tokenizer.count(block.text) <= maximum_tokens:
        return [_piece(block, [(0, len(block.text))])]
    finding = {
        "code": (
            "oversize_protected_block_split"
            if block.type in _PROTECTED
            else "oversize_block_split"
        ),
        "message": "A source block exceeded the hard token limit and was split at a deterministic Unicode boundary.",
    }
    return [
        _piece(block, [value], findings=(finding,))
        for value in _split_ranges(block.text, maximum_tokens, tokenizer, v3)
    ]


def _sections(
    document: CleanedDocumentV1,
    maximum_tokens: int,
    tokenizer: Utf8ByteTokenizer,
    v3: bool = False,
) -> list[list[_Piece]]:
    result: list[list[_Piece]] = []
    key: tuple[tuple[str, ...], int | None] | None = None
    for block in document.blocks:
        # A chunk is cited by one page number. Keep page boundaries even when
        # adjacent pages share the same heading path.
        block_key = (_section_path(block), block.page_number)
        if key != block_key:
            result.append([])
            key = block_key
        result[-1].extend(_block_pieces(block, maximum_tokens, tokenizer, v3))
    return [value for value in result if value]


def _joined_tokens(pieces: list[_Piece], tokenizer: Utf8ByteTokenizer) -> int:
    return tokenizer.count("\n\n".join(piece.text for piece in pieces))


def _word_start(text: str, start: int) -> int | None:
    """v3: the first position at or after start that does not cut a word."""
    if start <= 0 or not (text[start - 1].isalnum() and text[start].isalnum()):
        return start
    match = _WORD_START_V3.search(text, start)
    return match.end() if match and match.end() < len(text) else None


def _suffix_pieces(
    pieces: list[_Piece],
    overlap_tokens: int,
    tokenizer: Utf8ByteTokenizer,
    v3: bool = False,
) -> list[_Piece]:
    if overlap_tokens <= 0:
        return []
    selected: list[_Piece] = []
    remaining = overlap_tokens
    for piece in reversed(pieces):
        size = tokenizer.count(piece.text)
        if size <= remaining:
            selected.append(piece)
            remaining -= size
            continue
        if piece.protected or len(piece.mappings) != 1 or remaining <= 0:
            break
        mapping = piece.mappings[0]
        local_start = tokenizer.suffix_start(piece.text, len(piece.text), remaining)
        if v3:
            local_start = _word_start(piece.text, local_start)
            if local_start is None:
                break
        block_start = mapping.block_start + local_start
        if block_start < mapping.block_end:
            selected.append(_piece(mapping.block, [(block_start, mapping.block_end)]))
        break
    return list(reversed(selected))


def _word_points(piece: _Piece) -> list[int]:
    """Positions in a splittable piece where a v3 split falls between words."""
    if piece.protected or len(piece.mappings) != 1:
        return []
    text = piece.text
    return sorted(
        {
            *(match.end() for match in _BOUNDARY_V3.finditer(text)),
            *(match.end() for match in _SPACE_RUN.finditer(text)),
        }
        - {0, len(text)}
    )


def _split_at(piece: _Piece, point: int) -> tuple[_Piece, _Piece]:
    mapping = piece.mappings[0]
    middle = mapping.block_start + point
    return (
        _piece(mapping.block, [(mapping.block_start, middle)], piece.findings),
        _piece(mapping.block, [(middle, mapping.block_end)]),
    )


def _split_head(
    piece: _Piece, budget: int, tokenizer: Utf8ByteTokenizer
) -> tuple[_Piece, _Piece] | None:
    """v3: the longest head of a piece within budget that ends between words and
    leaves at least SHORT_CHUNK_TOKENS behind, and the rest of the piece."""
    if budget <= 0:
        return None
    end = tokenizer.prefix_end(piece.text, 0, budget)
    for point in reversed(_word_points(piece)):
        if point <= end and tokenizer.count(piece.text[point:]) >= SHORT_CHUNK_TOKENS:
            return _split_at(piece, point)
    return None


def _split_tail(
    previous: list[_Piece], remainder: list[_Piece], tokenizer: Utf8ByteTokenizer
) -> tuple[list[_Piece], list[_Piece]] | None:
    """v3: move the fewest closing words of the group before a short remainder onto
    it, so both reach SHORT_CHUNK_TOKENS; None when its last piece cannot split."""
    last = previous[-1]
    for point in reversed(_word_points(last)):
        head, tail = _split_at(last, point)
        if _joined_tokens([tail, *remainder], tokenizer) < SHORT_CHUNK_TOKENS:
            continue
        kept = [*previous[:-1], head]
        if _joined_tokens(kept, tokenizer) < SHORT_CHUNK_TOKENS:
            return None
        return kept, [tail, *remainder]
    return None


def _pack(
    pieces: list[_Piece],
    *,
    target_tokens: int,
    maximum_tokens: int,
    overlap_tokens: int,
    tokenizer: Utf8ByteTokenizer,
    v3: bool = False,
) -> list[list[_Piece]]:
    groups: list[list[_Piece]] = []
    current: list[_Piece] = []
    # Where the current group's own text starts, after the overlap it repeats.
    fresh = 0
    for piece in pieces:
        candidate = [*current, piece]
        should_flush = bool(current) and (
            _joined_tokens(current, tokenizer) >= target_tokens
            or _joined_tokens(candidate, tokenizer) > maximum_tokens
        )
        if (
            v3
            and should_flush
            and _joined_tokens(current[fresh:], tokenizer) < SHORT_CHUNK_TOKENS
        ):
            if _joined_tokens(candidate, tokenizer) <= maximum_tokens:
                # Its own text is too short to stand alone: keep filling it.
                should_flush = False
            elif split := _split_head(
                piece,
                maximum_tokens - _joined_tokens(current, tokenizer) - 2,
                tokenizer,
            ):
                # A heading or short line followed by a long split paragraph takes
                # the paragraph's opening words instead of standing alone.
                head, piece = split
                current = [*current, head]
        if should_flush:
            groups.append(current)
            overlap = _suffix_pieces(current, overlap_tokens, tokenizer, v3)
            while (
                overlap
                and _joined_tokens([*overlap, piece], tokenizer) > maximum_tokens
            ):
                overlap.pop(0)
            current = [*overlap, piece]
            fresh = len(overlap)
        else:
            current = candidate
    if current:
        groups.append(current)
    if v3 and len(groups) > 1:
        # A last group adding under 40 bytes of its own joins the group before it.
        remainder = groups[-1][fresh:]
        if _joined_tokens(remainder, tokenizer) >= SHORT_CHUNK_TOKENS:
            pass
        elif _joined_tokens([*groups[-2], *remainder], tokenizer) <= maximum_tokens:
            groups[-2:] = [[*groups[-2], *remainder]]
        elif moved := _split_tail(groups[-2], remainder, tokenizer):
            # The remainder takes the closing words before it instead of its
            # overlap, so the text still reads on without a gap.
            groups[-2:] = list(moved)
    return groups


def _group_page(group: list[_Piece]) -> tuple[bool, int | None]:
    pages = {piece.page_number for piece in group}
    return (len(pages) == 1, next(iter(pages)) if len(pages) == 1 else None)


def _packed_sections(
    sections: list[list[_Piece]],
    *,
    target_tokens: int,
    maximum_tokens: int,
    overlap_tokens: int,
    tokenizer: Utf8ByteTokenizer,
    merge_short: bool,
    v3: bool = False,
) -> list[tuple[list[_Piece], list[list[_Piece]]]]:
    """Pack each section, optionally merging short section starts backwards.

    Returns each group with the section segments it holds, so parent groups can pack
    their children segment by segment. Without merging every group is one segment
    and the result equals packing each section on its own.

    v3 also carries a short section that cannot join the chunk before it (the
    first section, or the first on its page) forward: its pieces open the next
    section on the same page, which is then packed as usual.
    """

    def short(group: list[_Piece]) -> bool:
        return _joined_tokens(group, tokenizer) < SHORT_CHUNK_TOKENS

    def can_join(left: list[_Piece], right: list[_Piece]) -> bool:
        return (
            _group_page(left) == _group_page(right)
            and _group_page(right)[0]
            and _joined_tokens([*left, *right], tokenizer) <= maximum_tokens
        )

    def repathed(segments, path):
        return [
            [replace(piece, section_path=path) for piece in segment]
            for segment in segments
        ]

    result: list[tuple[list[_Piece], list[list[_Piece]]]] = []
    pending: list[_Piece] | None = None
    for section in sections:
        if pending is not None:
            page = _group_page(pending)
            if page[0] and page == _group_page(section[:1]):
                # The carried text takes the receiving section's path.
                path = _common_path(section)
                section = [
                    *(replace(piece, section_path=path) for piece in pending),
                    *section,
                ]
            else:
                result.append((pending, [pending]))
            pending = None
        groups = [
            (group, [group])
            for group in _pack(
                section,
                target_tokens=target_tokens,
                maximum_tokens=maximum_tokens,
                overlap_tokens=overlap_tokens,
                tokenizer=tokenizer,
                v3=v3,
            )
        ]
        if merge_short and result and groups:
            previous, segments = result[-1]
            first, first_segments = groups[0]
            if short(first) and can_join(previous, first):
                # The merged chunk keeps the receiving chunk's section path; the
                # short text itself, heading included, stays in the evidence.
                moved = repathed(first_segments, _common_path(previous))
                result[-1] = (
                    [*previous, *(piece for segment in moved for piece in segment)],
                    [*segments, *moved],
                )
                groups = groups[1:]
        if v3 and len(groups) == 1 and short(groups[0][0]):
            pending = groups.pop()[0]
        result.extend(groups)
    if pending is not None:
        result.append((pending, [pending]))
    return result


def _common_path(pieces: list[_Piece]) -> tuple[str, ...]:
    if not pieces:
        return ()
    common = list(pieces[0].section_path)
    for piece in pieces[1:]:
        prefix = []
        for left, right in zip(common, piece.section_path, strict=False):
            if left != right:
                break
            prefix.append(left)
        common = prefix
    return tuple(common)


def _capped_prefix(body: str, tokenizer: Utf8ByteTokenizer) -> str:
    """'Section: … > <end of body>' within HEADING_PREFIX_BYTES."""
    frame = "Section: …\n\n"
    budget = HEADING_PREFIX_BYTES - tokenizer.count(frame)
    start = tokenizer.suffix_start(body, len(body), budget)
    return f"Section: …{body[start:]}\n\n"


def _opening_headings(pieces: list[_Piece]) -> set[str]:
    """The whole heading blocks a passage starts with, before any other text."""
    headings: set[str] = set()
    for piece in pieces:
        mapping = piece.mappings[0] if len(piece.mappings) == 1 else None
        if (
            mapping is None
            or mapping.block.type != "heading"
            or mapping.block_start != 0
            or mapping.block_end != len(mapping.block.text)
        ):
            break
        headings.add(mapping.block.text[:500])
    return headings


def _prepared(
    pieces: list[_Piece],
    *,
    ordinal: int,
    role: str,
    parent_ordinal: int | None,
    algorithm: str,
    tokenizer: Utf8ByteTokenizer,
    heading_prefix: bool,
    provenance: dict[str, Any],
    v3: bool = False,
) -> tuple[PreparedChunk, list[ChunkBlockSpanV1]]:
    evidence = "\n\n".join(piece.text for piece in pieces)
    path = _common_path(pieces)
    prefix_path = path
    if v3 and path:
        # Headings the passage already opens with are not repeated in its prefix.
        opening = _opening_headings(pieces)
        prefix_path = tuple(heading for heading in path if heading not in opening)
    prefix = (
        f"Section: {' > '.join(prefix_path)}\n\n"
        if heading_prefix and prefix_path
        else ""
    )
    if v3 and tokenizer.count(prefix) > HEADING_PREFIX_BYTES:
        prefix = _capped_prefix(" > ".join(prefix_path), tokenizer)
    elif (
        tokenizer.count(prefix) > HEADING_PREFIX_BYTES
        and tokenizer.count(prefix + evidence) > EMBEDDING_INPUT_BYTES
    ):
        # Spec 0012 D5: a long heading path is shortened from the front, keeping
        # its most specific headings, only where the full prefix would make the
        # passage too large to embed. Every passage that fitted is unchanged.
        prefix = _capped_prefix(" > ".join(path), tokenizer)
    mappings: list[ChunkBlockSpanV1] = []
    cursor = 0
    for index, piece in enumerate(pieces):
        if index:
            cursor += 2
        for mapping in piece.mappings:
            mappings.append(
                ChunkBlockSpanV1(
                    block_id=mapping.block.id,
                    block_ordinal=mapping.block.ordinal,
                    block_start_char=mapping.block_start,
                    block_end_char=mapping.block_end,
                    chunk_start_char=cursor + mapping.piece_start,
                    chunk_end_char=cursor + mapping.piece_end,
                )
            )
        cursor += len(piece.text)
    pages = {piece.page_number for piece in pieces}
    findings = tuple(value for piece in pieces for value in piece.findings)[:100]
    embedding_text = prefix + evidence
    return (
        PreparedChunk(
            ordinal=ordinal,
            page_number=next(iter(pages)) if len(pages) == 1 else None,
            start_char=0,
            end_char=len(evidence),
            text=evidence,
            embedding_text=embedding_text,
            token_count=tokenizer.count(evidence),
            embedding_token_count=tokenizer.count(embedding_text),
            chunk_role=role,
            parent_ordinal=parent_ordinal,
            findings=findings,
            provenance={
                **provenance,
                "section_path": list(path),
                "embedding_prefix": prefix,
                "chunk_algorithm": algorithm,
                "tokenizer": tokenizer.version,
            },
        ),
        mappings,
    )


def chunk_structured_document(
    document: CleanedDocumentV1,
    settings,
    *,
    provenance: dict[str, Any] | None = None,
) -> tuple[list[PreparedChunk], dict[int, list[ChunkBlockSpanV1]]]:
    tokenizer = tokenizer_for(settings.tokenizer_version)
    provenance = provenance or {}
    merge_short = settings.config_version in SHORT_CHUNK_MERGE_VERSIONS
    v3 = settings.config_version in V3_VERSIONS
    chunks: list[PreparedChunk] = []
    spans: dict[int, list[ChunkBlockSpanV1]] = {}

    if settings.algorithm == "section_token":
        sections = _sections(document, settings.maximum_tokens, tokenizer, v3)
        for group, _segments in _packed_sections(
            sections,
            target_tokens=settings.target_tokens,
            maximum_tokens=settings.maximum_tokens,
            overlap_tokens=settings.overlap_tokens,
            tokenizer=tokenizer,
            merge_short=merge_short,
            v3=v3,
        ):
            chunk, mapped = _prepared(
                group,
                ordinal=len(chunks),
                role="leaf",
                parent_ordinal=None,
                algorithm=settings.algorithm,
                tokenizer=tokenizer,
                heading_prefix=settings.add_heading_context,
                provenance=provenance,
                v3=v3,
            )
            chunks.append(chunk)
            spans[chunk.ordinal] = mapped
        return chunks, spans

    sections = _sections(document, settings.child_maximum_tokens, tokenizer, v3)
    for parent_group, segments in _packed_sections(
        sections,
        target_tokens=settings.parent_target_tokens,
        maximum_tokens=settings.parent_maximum_tokens,
        overlap_tokens=0,
        tokenizer=tokenizer,
        merge_short=merge_short,
        v3=v3,
    ):
        parent, parent_spans = _prepared(
            parent_group,
            ordinal=len(chunks),
            role="parent",
            parent_ordinal=None,
            algorithm=settings.algorithm,
            tokenizer=tokenizer,
            heading_prefix=False,
            provenance=provenance,
            v3=v3,
        )
        chunks.append(parent)
        spans[parent.ordinal] = parent_spans
        # Children pack within each section segment of the parent, so a merged
        # short segment joins the child before it rather than its overlap.
        for child_group, _child_segments in _packed_sections(
            segments,
            target_tokens=settings.child_target_tokens,
            maximum_tokens=settings.child_maximum_tokens,
            overlap_tokens=settings.child_overlap_tokens,
            tokenizer=tokenizer,
            merge_short=merge_short,
            v3=v3,
        ):
            child, child_spans = _prepared(
                child_group,
                ordinal=len(chunks),
                role="child",
                parent_ordinal=parent.ordinal,
                algorithm=settings.algorithm,
                tokenizer=tokenizer,
                heading_prefix=settings.add_heading_context,
                provenance=provenance,
                v3=v3,
            )
            chunks.append(child)
            spans[child.ordinal] = child_spans
    return chunks, spans
