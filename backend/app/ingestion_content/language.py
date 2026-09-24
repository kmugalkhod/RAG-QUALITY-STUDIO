"""Bounded, deterministic language metadata and saved policy enforcement."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.ingestion_content.contracts import (
    ExtractedDocumentV1,
    LanguageResult,
    QualityFinding,
)


MODEL_VERSION = "deterministic-script-v1"
MAX_SAMPLE_CHARACTERS = 50_000
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
_LATIN_MARKERS = {
    "en": {"the", "and", "is", "of", "to", "in", "for", "with"},
    "es": {"el", "la", "de", "y", "en", "para", "con", "que"},
    "fr": {"le", "la", "de", "et", "en", "pour", "avec", "que"},
    "de": {"der", "die", "das", "und", "in", "für", "mit", "ist"},
}


def _script(character: str) -> str | None:
    if not character.isalpha():
        return None
    name = unicodedata.name(character, "")
    for marker, language in (
        ("CYRILLIC", "ru"),
        ("ARABIC", "ar"),
        ("DEVANAGARI", "hi"),
        ("HIRAGANA", "ja"),
        ("KATAKANA", "ja"),
        ("HANGUL", "ko"),
        ("CJK", "zh"),
        ("IDEOGRAPH", "zh"),
    ):
        if marker in name:
            return language
    return "latin" if "LATIN" in name else "und"


def detect_language(text: str) -> LanguageResult:
    sample = text[:MAX_SAMPLE_CHARACTERS]
    scripts = Counter(filter(None, (_script(value) for value in sample)))
    letters = sum(scripts.values())
    if not letters:
        return LanguageResult(
            language="und", method="unicode-script", model_version=MODEL_VERSION
        )
    script, count = scripts.most_common(1)[0]
    confidence = count / letters
    language = script
    if script == "latin":
        words = [value.casefold() for value in _WORDS.findall(sample)]
        scores = {
            code: sum(word in markers for word in words)
            for code, markers in _LATIN_MARKERS.items()
        }
        language, matches = max(scores.items(), key=lambda value: (value[1], value[0]))
        if matches == 0:
            language = "und"
            confidence = min(confidence, 0.40)
        else:
            confidence = min(1.0, 0.55 + matches / max(10, len(words)))
    mixed = len([value for value in scripts.values() if value / letters >= 0.20]) > 1
    return LanguageResult(
        language=language,
        method="unicode-script-stopwords",
        model_version=MODEL_VERSION,
        confidence=round(confidence, 4),
        mixed=mixed,
    )


def apply_language_policy(document: ExtractedDocumentV1, policy) -> ExtractedDocumentV1:
    page_languages = {}
    for page in document.pages:
        page_text = "\n".join(
            block.text
            for block in document.blocks
            if block.page_number == page.page_number
        )
        page_languages[page.page_number] = detect_language(page_text)
    document_language = detect_language(
        "\n".join(block.text for block in document.blocks)
    )
    observed = {
        value.language for value in page_languages.values() if value.language != "und"
    }
    mixed = document_language.mixed or len(observed) > 1
    document_language = document_language.model_copy(update={"mixed": mixed})
    pages = [
        page.model_copy(update={"language": page_languages.get(page.page_number)})
        for page in document.pages
    ]
    findings = list(document.findings)
    decision = document.measurements.quality_decision

    if (
        policy.minimum_confidence > 0
        and document_language.confidence < policy.minimum_confidence
    ):
        findings.append(
            QualityFinding(
                code="language_confidence_low",
                severity="warning",
                message="Language confidence is below the saved threshold.",
                remediation="Review language metadata and OCR language packs.",
            )
        )
        if decision == "pass":
            decision = "warn"
    if policy.allowlist and document_language.language not in policy.allowlist:
        findings.append(
            QualityFinding(
                code="language_not_allowed",
                severity="error",
                message="Detected language is outside the saved allowlist.",
                remediation="Update the allowlist or exclude this source explicitly.",
            )
        )
        decision = policy.disallowed_action
    if mixed and policy.mixed_language_action != "allow":
        severity = "error" if policy.mixed_language_action == "fail" else "warning"
        findings.append(
            QualityFinding(
                code="mixed_languages",
                severity=severity,
                message="Multiple page or script languages were detected.",
                remediation="Review per-page language metadata and OCR settings.",
            )
        )
        if policy.mixed_language_action == "fail":
            decision = "fail"
        elif decision == "pass":
            decision = "warn"
    return document.model_copy(
        update={
            "language": document_language,
            "pages": pages,
            "findings": findings,
            "measurements": document.measurements.model_copy(
                update={"quality_decision": decision}
            ),
        }
    )
