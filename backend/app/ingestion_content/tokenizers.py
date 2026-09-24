"""Stable application-owned token counters for deterministic chunk boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Utf8ByteTokenizer:
    """A conservative, model-independent byte tokenizer.

    Every UTF-8 byte is one saved token. Byte-level model tokenizers cannot require
    more tokens than this count, while all returned boundaries remain valid Unicode
    character boundaries. The deliberately conservative count is reproducible without
    provider downloads or an ambient model vocabulary.
    """

    identity: str = "utf8_byte"
    version: str = "utf8-byte-v1"

    @staticmethod
    def count(text: str) -> int:
        return len(text.encode("utf-8"))

    @staticmethod
    def prefix_end(text: str, start: int, maximum_tokens: int) -> int:
        """Return the largest character boundary within the byte-token budget."""

        used = 0
        end = start
        while end < len(text):
            width = len(text[end].encode("utf-8"))
            if used + width > maximum_tokens:
                break
            used += width
            end += 1
        return end

    @staticmethod
    def suffix_start(text: str, end: int, maximum_tokens: int) -> int:
        """Return the smallest suffix character boundary within the budget."""

        used = 0
        start = end
        while start > 0:
            width = len(text[start - 1].encode("utf-8"))
            if used + width > maximum_tokens:
                break
            used += width
            start -= 1
        return start


TOKENIZERS = {Utf8ByteTokenizer.version: Utf8ByteTokenizer()}


def tokenizer_for(version: str) -> Utf8ByteTokenizer:
    try:
        return TOKENIZERS[version]
    except KeyError as exc:
        raise ValueError("Unsupported tokenizer version.") from exc


def tokenizer_capabilities() -> list[dict[str, str]]:
    return [
        {
            "id": value.identity,
            "version": value.version,
            "unit": "UTF-8 bytes (conservative token upper bound)",
        }
        for value in TOKENIZERS.values()
    ]
