"""Character error rate of OCR text against a hand-checked transcription (spec 0008, B4).

    python ocr_cer.py RAW.json FILE PAGE TRUTH.txt passages|rows

RAW.json is an `extract_baseline.py extract` output. The truth file is split into
passages (blank-line separated) or rows (one per line); each is aligned to the
best-matching stretch of the page's OCR text (free start and end), so block order
and text outside the checked region do not count. Whitespace is collapsed on both
sides; every other character difference counts. `rows` also reports how many
values (words after the row name, without footnote markers such as `4/`) are exact.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path


def _normal(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _align(truth: str, text: str) -> tuple[int, str]:
    """Edit distance of truth against its best-matching substring of text."""

    previous = [0] * (len(text) + 1)
    starts = list(range(len(text) + 1))
    for i, truth_char in enumerate(truth, 1):
        current = [i] + [0] * len(text)
        current_starts = [0] + [0] * len(text)
        for j, text_char in enumerate(text, 1):
            options = (
                (previous[j - 1] + (truth_char != text_char), starts[j - 1]),
                (previous[j] + 1, starts[j]),
                (current[j - 1] + 1, current_starts[j - 1]),
            )
            current[j], current_starts[j] = min(options)
        previous, starts = current, current_starts
    end = min(range(len(text) + 1), key=previous.__getitem__)
    return previous[end], text[starts[end] : end]


def _values(row: str, name_words: int) -> list[str]:
    return [w for w in row.split()[name_words:] if not re.fullmatch(r"\d/", w)]


def main(raw: str, name: str, page: str, truth_path: str, mode: str) -> None:
    document = json.loads(Path(raw).read_text(encoding="utf-8"))["files"][name]
    text = _normal(
        " ".join(b["text"] for b in document["blocks"] if b["page"] == int(page))
    )
    truth = Path(truth_path).read_text(encoding="utf-8")
    units = (
        [_normal(p) for p in re.split(r"\n\s*\n", truth) if p.strip()]
        if mode == "passages"
        else [_normal(line) for line in truth.splitlines() if line.strip()]
    )
    errors = characters = values_total = values_exact = 0
    for unit in units:
        distance, matched = _align(unit, text)
        errors += distance
        characters += len(unit)
        if mode == "rows":
            name_words = len(re.match(r"[^\d]*", unit).group(0).split())
            expected = _values(unit, name_words)
            found = _values(matched, name_words)
            matcher = difflib.SequenceMatcher(a=expected, b=found, autojunk=False)
            exact = sum(block.size for block in matcher.get_matching_blocks())
            values_total += len(expected)
            values_exact += exact
            if exact < len(expected) or distance:
                print(f"  {distance:>3} | {unit}\n      | {matched}")
        elif distance:
            print(f"  {distance:>3} errors in: {unit[:60]}...")
    print(
        f"{name} p{page}: {errors} errors / {characters} characters, "
        f"CER {errors / characters:.2%}"
    )
    if mode == "rows":
        print(
            f"values exact: {values_exact} / {values_total} "
            f"({values_exact / values_total:.1%})"
        )


if __name__ == "__main__":
    main(*sys.argv[1:6])
