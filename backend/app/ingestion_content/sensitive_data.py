"""Deterministic sensitive-data detection and irreversible canonical redaction.

The detector intentionally supports a small reviewed entity set. It never returns or
persists matched values. Pattern detection reduces exposure; it is not complete PII
detection and must not be represented as such.
"""

from __future__ import annotations

import ipaddress
import re
import time
from collections import Counter
from dataclasses import dataclass

from app.ingestion_content.contracts import (
    CanonicalBlock,
    CleanedDocumentV1,
    SensitiveDataFinding,
    TransformAudit,
    TransformChange,
)
from app.ingestion_content.processing import IngestionStageError


DETECTOR_VERSION = "deterministic-patterns-v1"
MAX_FINDINGS = 10_000

_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]{1,64}@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}(?![A-Za-z0-9_\-])"
)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_US_SSN = re.compile(
    r"(?<!\d)(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}(?!\d)"
)
_AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]\d{4}[ -]\d{4}(?!\d)")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
_PHONE = re.compile(
    r"(?<![\w\d])(?:\+\d{1,3}[ .-]?)?"
    r"(?:\(\d{2,4}\)|\d{2,4})[ .-]"
    r"(?:\d{2,4}[ .-]){1,3}\d{2,4}(?![\w\d])"
)
_SECRET_PATTERNS = (
    (
        "openai_key",
        re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}(?![A-Za-z0-9])"),
        0,
    ),
    ("aws_access_key", re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"), 0),
    (
        "github_token",
        re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}(?![A-Za-z0-9])"),
        0,
    ),
    (
        "slack_token",
        re.compile(r"(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{16,}(?![A-Za-z0-9])"),
        0,
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)(?:api[_-]?key|access[_-]?token|secret|password)"
            r"\s*[:=]\s*[\"']?([A-Za-z0-9_./+=-]{7,}[A-Za-z0-9_+=])"
        ),
        1,
    ),
)
_PLACEHOLDERS = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "ip_address": "[IP_ADDRESS]",
    "government_id": "[GOVERNMENT_ID]",
    "payment_card": "[PAYMENT_CARD]",
    "api_secret": "[API_SECRET]",
}
_PRIORITY = {
    "api_secret": 0,
    "payment_card": 1,
    "government_id": 2,
    "email": 3,
    "ip_address": 4,
    "phone": 5,
}


@dataclass(frozen=True)
class _Match:
    entity_class: str
    detector: str
    start: int
    end: int
    subtype: str | None = None


class SensitiveDataDropError(IngestionStageError):
    """Safe drop decision carrying location-only findings for item inspection."""

    def __init__(self, findings: list[SensitiveDataFinding]):
        super().__init__(
            "clean",
            "sensitive_data_drop_document",
            "The saved sensitive-data policy excluded this item.",
        )
        self.findings = tuple(findings)


def _luhn(value: str) -> bool:
    digits = [int(item) for item in value]
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def _verhoeff(value: str) -> bool:
    checksum = 0
    for index, digit in enumerate(reversed(value)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[index % 8][int(digit)]]
    return checksum == 0


def _matches(text: str, policy) -> list[_Match]:
    enabled = {rule.entity_class for rule in policy.rules}
    values: list[_Match] = []
    if "email" in enabled:
        values.extend(
            _Match("email", "email_pattern", item.start(), item.end())
            for item in _EMAIL.finditer(text)
        )
    if "payment_card" in enabled:
        for item in _CARD.finditer(text):
            digits = re.sub(r"\D", "", item.group())
            if 13 <= len(digits) <= 19 and _luhn(digits):
                values.append(
                    _Match(
                        "payment_card",
                        "payment_card_luhn",
                        item.start(),
                        item.end(),
                    )
                )
    if "government_id" in enabled:
        if "us_ssn" in policy.government_id_formats:
            values.extend(
                _Match(
                    "government_id",
                    "government_id_pattern",
                    item.start(),
                    item.end(),
                    "us_ssn",
                )
                for item in _US_SSN.finditer(text)
            )
        if "in_aadhaar" in policy.government_id_formats:
            for item in _AADHAAR.finditer(text):
                digits = re.sub(r"\D", "", item.group())
                if _verhoeff(digits):
                    values.append(
                        _Match(
                            "government_id",
                            "government_id_checksum",
                            item.start(),
                            item.end(),
                            "in_aadhaar",
                        )
                    )
    if "ip_address" in enabled:
        for detector, pattern in (("ipv4", _IPV4), ("ipv6", _IPV6)):
            for item in pattern.finditer(text):
                try:
                    ipaddress.ip_address(item.group())
                except ValueError:
                    continue
                values.append(
                    _Match(
                        "ip_address",
                        "ip_address_parser",
                        item.start(),
                        item.end(),
                        detector,
                    )
                )
    if "api_secret" in enabled:
        for subtype, pattern, group in _SECRET_PATTERNS:
            for item in pattern.finditer(text):
                values.append(
                    _Match(
                        "api_secret",
                        "secret_token_pattern",
                        item.start(group),
                        item.end(group),
                        subtype,
                    )
                )
    if "phone" in enabled:
        for item in _PHONE.finditer(text):
            digits = re.sub(r"\D", "", item.group())
            if 10 <= len(digits) <= 15:
                values.append(
                    _Match("phone", "phone_pattern", item.start(), item.end())
                )

    selected: list[_Match] = []
    for candidate in sorted(
        values,
        key=lambda value: (
            value.start,
            _PRIORITY[value.entity_class],
            -(value.end - value.start),
            value.detector,
        ),
    ):
        if any(
            candidate.start < current.end and current.start < candidate.end
            for current in selected
        ):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda value: (value.start, value.end))


def apply_sensitive_data_policy(
    document: CleanedDocumentV1,
    policy,
) -> tuple[CleanedDocumentV1, TransformAudit | None]:
    """Apply a saved policy and return redacted content plus location-only findings."""

    if not policy.enabled:
        return document, None
    started = time.perf_counter_ns()
    actions = {rule.entity_class: rule.action for rule in policy.rules}
    findings: list[SensitiveDataFinding] = []
    block_matches: dict[str, list[_Match]] = {}
    for block in document.blocks:
        matches = _matches(block.text, policy)
        if matches:
            block_matches[block.id] = matches
        for match in matches:
            findings.append(
                SensitiveDataFinding(
                    entity_class=match.entity_class,
                    detector=match.detector,
                    subtype=match.subtype,
                    action=actions[match.entity_class],
                    block_id=block.id,
                    block_ordinal=block.ordinal,
                    page_number=block.page_number,
                    start_char=match.start,
                    end_char=match.end,
                )
            )
            if len(findings) > MAX_FINDINGS:
                raise IngestionStageError(
                    "clean",
                    "too_many_sensitive_findings",
                    "Sensitive-data findings exceed the deterministic safety limit.",
                )
    dropped = [item for item in findings if item.action == "drop_document"]
    if dropped:
        raise SensitiveDataDropError(findings)

    rewritten: list[CanonicalBlock] = []
    changes: list[TransformChange] = []
    for block in document.blocks:
        matches = block_matches.get(block.id, [])
        if not matches:
            rewritten.append(block)
            continue
        parts: list[str] = []
        cursor = 0
        for match in matches:
            parts.append(block.text[cursor : match.start])
            parts.append(_PLACEHOLDERS[match.entity_class])
            cursor = match.end
        parts.append(block.text[cursor:])
        rewritten.append(block.model_copy(update={"text": "".join(parts)}))
        changes.append(
            TransformChange(
                block_id=block.id,
                action="rewritten",
                reason="sensitive_data_redacted",
                count=len(matches),
            )
        )
    counts = Counter(item.entity_class for item in findings)
    audit = TransformAudit(
        transform="sensitive_data_redaction",
        version=DETECTOR_VERSION,
        changed_blocks=len(changes),
        removed_blocks=0,
        duration_ms=max(0, (time.perf_counter_ns() - started) // 1_000_000),
        metrics={
            "finding_count": len(findings),
            **{f"{entity}_count": count for entity, count in sorted(counts.items())},
            "irreversible": True,
        },
        changes=changes[:200],
    )
    from app.ingestion_content.canonical import document_hash

    pages = sorted(
        {block.page_number for block in rewritten if block.page_number is not None}
    )
    measurements = document.measurements.model_copy(
        update={
            "character_count": sum(len(block.text) for block in rewritten),
            "block_count": len(rewritten),
            "page_character_counts": [
                sum(
                    len(block.text)
                    for block in rewritten
                    if block.page_number == page_number
                )
                for page_number in pages
            ],
            "page_block_counts": [
                sum(block.page_number == page_number for block in rewritten)
                for page_number in pages
            ],
        }
    )
    redacted = document.model_copy(
        update={
            "blocks": rewritten,
            "sensitive_findings": findings,
            "sensitive_data_applied": True,
            "transforms": [*document.transforms, audit],
            "measurements": measurements,
            "output_hash": document_hash(rewritten),
        }
    )
    return redacted, audit
