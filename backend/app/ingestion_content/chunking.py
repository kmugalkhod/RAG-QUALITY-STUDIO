"""Deterministic structure-aware and parent/child chunk construction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.ingestion_content.contracts import (
    CanonicalBlock,
    ChunkBlockSpanV1,
    CleanedDocumentV1,
)
from app.ingestion_content.processing import PreparedChunk
from app.ingestion_content.tokenizers import Utf8ByteTokenizer, tokenizer_for


_BOUNDARY = re.compile(r"(?:\n{2,}|(?<=[.!?])\s+|\n)")
_MARKDOWN_DIVIDER = re.compile(r"^\s*\|?\s*:?-{3,}")
_PROTECTED = {"list_item", "table", "code"}


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
    text: str, maximum_tokens: int, tokenizer: Utf8ByteTokenizer
) -> list[tuple[int, int]]:
    boundaries = [match.end() for match in _BOUNDARY.finditer(text)]
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        cap = tokenizer.prefix_end(text, start, maximum_tokens)
        if cap == len(text):
            ranges.append((start, cap))
            break
        if cap <= start:
            cap = start + 1
        preferred = max(
            (value for value in boundaries if start < value <= cap), default=cap
        )
        ranges.append((start, preferred))
        start = preferred
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
    block: CanonicalBlock, maximum_tokens: int, tokenizer: Utf8ByteTokenizer
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
            for value in _split_ranges(block.text, maximum_tokens, tokenizer)
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
                row_text, maximum_tokens - header_tokens, tokenizer
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
    block: CanonicalBlock, maximum_tokens: int, tokenizer: Utf8ByteTokenizer
) -> list[_Piece]:
    if block.type == "table":
        return _table_pieces(block, maximum_tokens, tokenizer)
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
        for value in _split_ranges(block.text, maximum_tokens, tokenizer)
    ]


def _sections(
    document: CleanedDocumentV1,
    maximum_tokens: int,
    tokenizer: Utf8ByteTokenizer,
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
        result[-1].extend(_block_pieces(block, maximum_tokens, tokenizer))
    return [value for value in result if value]


def _joined_tokens(pieces: list[_Piece], tokenizer: Utf8ByteTokenizer) -> int:
    return tokenizer.count("\n\n".join(piece.text for piece in pieces))


def _suffix_pieces(
    pieces: list[_Piece], overlap_tokens: int, tokenizer: Utf8ByteTokenizer
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
        block_start = mapping.block_start + local_start
        if block_start < mapping.block_end:
            selected.append(_piece(mapping.block, [(block_start, mapping.block_end)]))
        break
    return list(reversed(selected))


def _pack(
    pieces: list[_Piece],
    *,
    target_tokens: int,
    maximum_tokens: int,
    overlap_tokens: int,
    tokenizer: Utf8ByteTokenizer,
) -> list[list[_Piece]]:
    groups: list[list[_Piece]] = []
    current: list[_Piece] = []
    for piece in pieces:
        candidate = [*current, piece]
        should_flush = bool(current) and (
            _joined_tokens(current, tokenizer) >= target_tokens
            or _joined_tokens(candidate, tokenizer) > maximum_tokens
        )
        if should_flush:
            groups.append(current)
            overlap = _suffix_pieces(current, overlap_tokens, tokenizer)
            while (
                overlap
                and _joined_tokens([*overlap, piece], tokenizer) > maximum_tokens
            ):
                overlap.pop(0)
            current = [*overlap, piece]
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


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
) -> tuple[PreparedChunk, list[ChunkBlockSpanV1]]:
    evidence = "\n\n".join(piece.text for piece in pieces)
    path = _common_path(pieces)
    prefix = f"Section: {' > '.join(path)}\n\n" if heading_prefix and path else ""
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
    chunks: list[PreparedChunk] = []
    spans: dict[int, list[ChunkBlockSpanV1]] = {}

    if settings.algorithm == "section_token":
        sections = _sections(document, settings.maximum_tokens, tokenizer)
        for section in sections:
            for group in _pack(
                section,
                target_tokens=settings.target_tokens,
                maximum_tokens=settings.maximum_tokens,
                overlap_tokens=settings.overlap_tokens,
                tokenizer=tokenizer,
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
                )
                chunks.append(chunk)
                spans[chunk.ordinal] = mapped
        return chunks, spans

    sections = _sections(document, settings.child_maximum_tokens, tokenizer)
    for section in sections:
        parent_groups = _pack(
            section,
            target_tokens=settings.parent_target_tokens,
            maximum_tokens=settings.parent_maximum_tokens,
            overlap_tokens=0,
            tokenizer=tokenizer,
        )
        for parent_group in parent_groups:
            parent, parent_spans = _prepared(
                parent_group,
                ordinal=len(chunks),
                role="parent",
                parent_ordinal=None,
                algorithm=settings.algorithm,
                tokenizer=tokenizer,
                heading_prefix=False,
                provenance=provenance,
            )
            chunks.append(parent)
            spans[parent.ordinal] = parent_spans
            for child_group in _pack(
                parent_group,
                target_tokens=settings.child_target_tokens,
                maximum_tokens=settings.child_maximum_tokens,
                overlap_tokens=settings.child_overlap_tokens,
                tokenizer=tokenizer,
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
                )
                chunks.append(child)
                spans[child.ordinal] = child_spans
    return chunks, spans
