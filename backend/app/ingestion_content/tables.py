"""Header-repeating table row groups shared by the v2 PDF and structured-file extractors."""

from __future__ import annotations

import json
from typing import Any

# Block attributes are limited to 16 KiB; groups keep a margin below that limit.
TABLE_ATTRIBUTE_BUDGET = 15_500


def bounded_table_grid(
    rows: list[list[Any]],
    *,
    max_rows: int,
    max_columns: int,
    max_cell_characters: int | None,
) -> tuple[list[list[str]], bool]:
    """Pad rows to one width and apply the caller's safety limits."""

    limited = len(rows) > max_rows or any(len(row) > max_columns for row in rows)
    bounded = []
    for row in rows[:max_rows]:
        cells = []
        for cell in row[:max_columns]:
            value = "" if cell is None else str(cell)
            if max_cell_characters is not None and len(value) > max_cell_characters:
                value = value[:max_cell_characters]
                limited = True
            cells.append(value)
        bounded.append(cells)
    width = max((len(row) for row in bounded), default=0)
    return [row + [""] * (width - len(row)) for row in bounded], limited


def _markdown_line(row: list[str]) -> str:
    cells = (
        cell.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
        for cell in row
    )
    return "| " + " | ".join(cells) + " |"


def _plain_line(row: list[str]) -> str:
    return "\t".join(cell.replace("\t", " ").replace("\n", " ") for cell in row)


def render_table(grid: list[list[str]]) -> tuple[str, str]:
    """Markdown and tab-separated renderings with the first row as the header."""

    width = max((len(row) for row in grid), default=0)
    markdown = ""
    if grid and width:
        lines = [_markdown_line(grid[0])]
        lines.append("| " + " | ".join(["---"] * width) + " |")
        lines.extend(_markdown_line(row) for row in grid[1:])
        markdown = "\n".join(lines)
    plain = "\n".join(_plain_line(row) for row in grid)
    return markdown, plain


def _group(
    header: list[str],
    body: list[list[str]],
    mode: str,
    *,
    base: dict[str, Any],
    table: dict[str, Any],
    structured: bool = True,
) -> tuple[str, dict[str, Any]]:
    markdown, plain = render_table([header, *body])
    evidence = plain if mode == "plain_text" else markdown
    rendering = "plain_text" if mode == "plain_text" else "markdown"
    if not structured:
        # The evidence text stays whole; only the structured copies are left out.
        return evidence or "[Empty table]", {
            **base,
            "table": {**table, "header_row": header, "rows_omitted": True},
            "evidence_rendering": rendering,
        }
    return evidence or "[Empty table]", {
        **base,
        "table": {**table, "rows": [header, *body], "header_row": header},
        "markdown": markdown,
        "plain_text": plain,
        "evidence_rendering": rendering,
    }


def _attribute_bytes(attributes: dict[str, Any]) -> int:
    return len(json.dumps(attributes, ensure_ascii=True).encode())


def _json_length(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=True))


def _row_cost(row: list[str]) -> int:
    """Bytes one row adds to group attributes: its list and two rendered lines.

    JSON escaping is per character, so row costs add up; each row also adds a ", "
    list separator and a newline before its line in both renderings.
    """

    return (
        _json_length(row)
        + 2
        + _json_length("\n" + _markdown_line(row))
        - 2
        + _json_length("\n" + _plain_line(row))
        - 2
    )


def table_row_groups(
    rows: list[list[Any]],
    mode: str,
    *,
    table_id: str,
    max_rows: int,
    max_columns: int,
    max_cell_characters: int | None,
    base_attributes: dict[str, Any] | None = None,
    table_fields: dict[str, Any] | None = None,
) -> tuple[list[tuple[str, dict[str, Any], int, int]], bool]:
    """Split one table into consecutive groups that each repeat the header row.

    Returns (evidence, attributes, first grid row, last grid row) per group and
    whether a safety limit cut the table. A row too large for the attribute budget
    becomes its own group with full evidence text but no structured row copy.
    Splitting alone loses nothing and is not a quality issue.
    """

    grid, limited = bounded_table_grid(
        rows,
        max_rows=max_rows,
        max_columns=max_columns,
        max_cell_characters=max_cell_characters,
    )
    if not grid:
        return [], limited
    base = dict(base_attributes or {})
    header, body = grid[0], grid[1:]
    shape = {
        **(table_fields or {}),
        "table_id": table_id,
        "row_count": len(rows),
        "column_count": max((len(row) for row in rows), default=0),
        "truncated": limited,
    }
    # Sizes are measured with the widest placeholder values so final groups fit.
    widest = max(max_rows, len(rows))
    probe = {
        **shape,
        "group_index": widest,
        "group_count": widest,
        "row_start": widest,
        "row_end": widest,
        "header_repeated": False,
    }

    def size(group_body: list[list[str]]) -> int:
        return _attribute_bytes(
            _group(header, group_body, mode, base=base, table=probe)[1]
        )

    empty = size([])
    partitions: list[tuple[list[list[str]], bool]] = []
    current: list[list[str]] = []
    used = empty
    for row in body:
        cost = _row_cost(row)
        if current and used + cost > TABLE_ATTRIBUTE_BUDGET:
            partitions.append((current, True))
            current, used = [], empty
        if not current and empty + cost > TABLE_ATTRIBUTE_BUDGET:
            partitions.append(([row], False))
            continue
        current.append(row)
        used += cost
    if current or not partitions:
        partitions.append((current, True))
    # Confirm each estimated group exactly; overflowing rows start a new group.
    index = 0
    while index < len(partitions):
        group_body, structured = partitions[index]
        moved: list[list[str]] = []
        while (
            structured
            and len(group_body) > 1
            and size(group_body) > TABLE_ATTRIBUTE_BUDGET
        ):
            moved.insert(0, group_body.pop())
        if moved:
            partitions.insert(index + 1, (moved, True))
        index += 1

    groups = []
    first = 1
    for index, (group_body, structured) in enumerate(partitions):
        last = first + len(group_body) - 1
        table = {
            **shape,
            "group_index": index,
            "group_count": len(partitions),
            "row_start": first,
            "row_end": last,
            "header_repeated": index > 0,
        }
        evidence, attributes = _group(
            header, group_body, mode, base=base, table=table, structured=structured
        )
        if structured and _attribute_bytes(attributes) > TABLE_ATTRIBUTE_BUDGET:
            evidence, attributes = _group(
                header, group_body, mode, base=base, table=table, structured=False
            )
        if _attribute_bytes(attributes) > TABLE_ATTRIBUTE_BUDGET:
            # Only a very wide header can still exceed the budget here.
            table = {
                key: value
                for key, value in attributes["table"].items()
                if key not in {"rows", "header_row"}
            }
            attributes = {
                **base,
                "table": {**table, "rows_omitted": True, "header_omitted": True},
                "evidence_rendering": attributes["evidence_rendering"],
            }
        groups.append((evidence, attributes, first, last))
        first = last + 1
    return groups, limited
