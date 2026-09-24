"""Deterministic structure-aware cleaning over the canonical extracted document.

Transforms operate only on immutable canonical blocks. Audits intentionally retain
bounded attribution rather than source text; the API reconstructs before/after text
from the immutable extracted and cleaned derivations.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from collections import Counter
from typing import Iterable

from app.ingestion_content.contracts import (
    CanonicalBlock,
    CleanedDocumentV1,
    ExtractedDocumentV1,
    TransformAudit,
    TransformChange,
)
from app.ingestion_content.processing import (
    IngestionStageError,
    STRUCTURE_CLEANER_VERSION,
)


_SPACE = re.compile(r"\s+")
_SINGLE_LINE_BREAK = re.compile(r"(?<!\n)\n(?!\n)")
_DEHYPHENATE = re.compile(r"([^\W\d_])-\s*\n\s*([^\W\d_])", re.UNICODE)
_COOKIE_HINTS = ("cookie", "consent", "privacy-banner", "gdpr")
_PROTECTED_DEFAULT = {"table", "list_item", "code", "quote", "footnote"}


def default_structure_steps() -> list[dict]:
    """Return the named server-supported profile without mutating a saved draft."""

    return [
        {
            "id": "preserve-structure",
            "type": "preserve_structure",
            "enabled": True,
            "block_types": ["table", "list_item", "code", "quote", "footnote"],
        },
        {
            "id": "unicode-normalize",
            "type": "unicode_normalize",
            "enabled": True,
            "form": "NFC",
        },
        {
            "id": "remove-controls",
            "type": "remove_control_characters",
            "enabled": True,
        },
        {
            "id": "repeated-margins",
            "type": "remove_repeated_headers_footers",
            "enabled": True,
            "minimum_page_ratio": 0.6,
            "minimum_pages": 3,
            "margin_ratio": 0.12,
        },
        {
            "id": "reflow-pdf-lines",
            "type": "reflow_pdf_lines",
            "enabled": True,
            "block_types": ["paragraph", "unknown"],
        },
        {
            "id": "dehyphenate",
            "type": "dehyphenate",
            "enabled": True,
            "mode": "conservative",
        },
        {
            "id": "website-main-content",
            "type": "website_main_content",
            "enabled": True,
            "remove_semantic_chrome": True,
            "remove_cookie_banners": True,
            "remove_repeated_site_chrome": True,
            "minimum_page_ratio": 0.6,
        },
        {
            "id": "remove-empty-blocks",
            "type": "remove_empty_blocks",
            "enabled": True,
            "minimum_characters": 1,
        },
        {
            "id": "validate-useful-content",
            "type": "validate_useful_content",
            "enabled": True,
            "minimum_characters": 1,
            "maximum_characters": 2_000_000,
        },
    ]


def _fingerprint(value: str) -> str:
    return _SPACE.sub(" ", value).strip().casefold()


def website_text_fingerprints(
    documents: Iterable[ExtractedDocumentV1], minimum_page_ratio: float = 0.6
) -> set[str]:
    """Return bounded cross-page text fingerprints repeated across a website run."""

    docs = list(documents)
    if len(docs) < 3:
        return set()
    counts: Counter[str] = Counter()
    for document in docs:
        counts.update(
            {
                value
                for block in document.blocks[:10_000]
                if (value := _fingerprint(block.text)) and len(value) <= 500
            }
        )
    return {
        value
        for value, count in counts.items()
        if count / len(docs) >= minimum_page_ratio
    }


def _changed(block: CanonicalBlock, text: str) -> CanonicalBlock:
    attributes = dict(block.attributes)
    cleaning = dict(attributes.get("cleaning") or {})
    cleaning["parent_block_ids"] = [block.id]
    attributes["cleaning"] = cleaning
    return block.model_copy(update={"text": text, "attributes": attributes})


def _audit(
    transform: str,
    started: int,
    changes: list[TransformChange],
    *,
    metrics: dict[str, int | float | str | bool] | None = None,
) -> TransformAudit:
    return TransformAudit(
        transform=transform,
        version=STRUCTURE_CLEANER_VERSION,
        changed_blocks=sum(change.action == "rewritten" for change in changes),
        removed_blocks=sum(change.action == "removed" for change in changes),
        duration_ms=max(0, (time.perf_counter_ns() - started) // 1_000_000),
        metrics=metrics or {},
        changes=changes[:200],
    )


def _rewrite(
    blocks: list[CanonicalBlock],
    transform: str,
    rewrite,
    *,
    protected: set[str] | None = None,
):
    started = time.perf_counter_ns()
    output = []
    changes = []
    units = 0
    protected = protected or set()
    for block in blocks:
        if block.type in protected:
            output.append(block)
            continue
        value, count = rewrite(block)
        units += count
        if not value:
            changes.append(
                TransformChange(
                    block_id=block.id,
                    action="removed",
                    reason=transform,
                    count=max(1, count),
                )
            )
        elif value != block.text:
            output.append(_changed(block, value))
            changes.append(
                TransformChange(
                    block_id=block.id,
                    action="rewritten",
                    reason=transform,
                    count=max(1, count),
                )
            )
        else:
            output.append(block)
    return output, _audit(transform, started, changes, metrics={"change_count": units})


def _unicode(block: CanonicalBlock, form: str):
    value = unicodedata.normalize(form, block.text)
    return value, sum(left != right for left, right in zip(block.text, value)) + abs(
        len(block.text) - len(value)
    )


def _controls(block: CanonicalBlock):
    removed = 0
    values = []
    for value in block.text:
        unsupported = unicodedata.category(value) in {"Cc", "Cf"} and value not in {
            "\n",
            "\r",
            "\t",
            "\u200c",
            "\u200d",
        }
        if unsupported:
            removed += 1
        else:
            values.append(value)
    return "".join(values), removed


def _reflow(block: CanonicalBlock, allowed: set[str]):
    if block.type not in allowed or "\n" not in block.text:
        return block.text, 0
    parts = []
    changed = 0
    for paragraph in re.split(r"(\n\s*\n)", block.text):
        if not paragraph or re.fullmatch(r"\n\s*\n", paragraph):
            parts.append(paragraph)
            continue

        def replacement(match):
            nonlocal changed
            before = paragraph[match.start() - 1] if match.start() else ""
            after = paragraph[match.end()] if match.end() < len(paragraph) else ""
            if (
                before
                and after
                and before != "-"
                and not before.isspace()
                and not after.isspace()
            ):
                changed += 1
                return " "
            return match.group(0)

        parts.append(_SINGLE_LINE_BREAK.sub(replacement, paragraph))
    return "".join(parts), changed


def _dehyphenate(block: CanonicalBlock):
    count = 0

    def replacement(match):
        nonlocal count
        left, right = match.group(1), match.group(2)
        if left.islower() and right.islower():
            count += 1
            return left + right
        return match.group(0)

    return _DEHYPHENATE.sub(replacement, block.text), count


def _remove_repeated_headers_footers(blocks, step, page_count, protected):
    started = time.perf_counter_ns()
    if page_count < step.minimum_pages:
        return blocks, _audit(
            step.type,
            started,
            [],
            metrics={"candidate_count": 0, "minimum_pages_met": False},
        )
    candidates: dict[str, set[int]] = {}
    for block in blocks:
        box = block.bounding_box
        if (
            block.page_number is None
            or box is None
            or block.type in protected
            or (box.top > step.margin_ratio and box.bottom < 1 - step.margin_ratio)
        ):
            continue
        value = _fingerprint(block.text)
        if value:
            candidates.setdefault(value, set()).add(block.page_number)
    repeated = {
        value
        for value, pages in candidates.items()
        if len(pages) / page_count >= step.minimum_page_ratio
    }
    output = []
    changes = []
    for block in blocks:
        box = block.bounding_box
        at_margin = box is not None and (
            box.top <= step.margin_ratio or box.bottom >= 1 - step.margin_ratio
        )
        if (
            block.page_number is not None
            and block.type not in protected
            and at_margin
            and _fingerprint(block.text) in repeated
        ):
            changes.append(
                TransformChange(
                    block_id=block.id,
                    action="removed",
                    reason="repeated_page_margin_text",
                )
            )
        else:
            output.append(block)
    return output, _audit(
        step.type,
        started,
        changes,
        metrics={
            "candidate_count": len(candidates),
            "fingerprints_removed": len(repeated),
        },
    )


def _remove_empty(blocks, step, protected):
    started = time.perf_counter_ns()
    output = []
    changes = []
    retained = 0
    for block in blocks:
        near_empty = len(_SPACE.sub("", block.text)) < step.minimum_characters
        if not near_empty:
            output.append(block)
        elif block.type in protected:
            output.append(block)
            retained += 1
            changes.append(
                TransformChange(
                    block_id=block.id,
                    action="retained",
                    reason="protected_block_type",
                )
            )
        else:
            changes.append(
                TransformChange(
                    block_id=block.id,
                    action="removed",
                    reason="empty_or_near_empty",
                )
            )
    return output, _audit(
        step.type,
        started,
        changes,
        metrics={"protected_blocks_retained": retained},
    )


def _remove_literals(blocks, step, protected):
    allowed = set(step.block_types) - protected

    def rewrite(block):
        if block.type not in allowed:
            return block.text, 0
        value = block.text
        count = 0
        for literal in step.values:
            count += value.count(literal)
            value = value.replace(literal, "")
        return value, count

    return _rewrite(blocks, step.type, rewrite)


def _selector_match(block: CanonicalBlock, selector: str) -> bool:
    selectors = block.attributes.get("html_selectors")
    return isinstance(selectors, list) and selector in selectors


def _website_selectors(blocks, step):
    started = time.perf_counter_ns()
    output = []
    changes = []
    for block in blocks:
        is_web = (
            block.source_span.kind == "provider_block"
            and getattr(block.source_span, "provider", None) == "website"
        )
        included = not step.include or any(
            _selector_match(block, selector) for selector in step.include
        )
        excluded = any(_selector_match(block, selector) for selector in step.exclude)
        if is_web and (not included or excluded):
            changes.append(
                TransformChange(
                    block_id=block.id,
                    action="removed",
                    reason="selector_excluded" if excluded else "selector_not_included",
                )
            )
        else:
            output.append(block)
    return output, _audit(step.type, started, changes)


def _website_main(blocks, step, repeated_fingerprints):
    started = time.perf_counter_ns()
    output = []
    changes = []
    web_blocks = [
        block
        for block in blocks
        if block.source_span.kind == "provider_block"
        and getattr(block.source_span, "provider", None) == "website"
    ]
    web_block_ids = {block.id for block in web_blocks}
    has_main = any(block.attributes.get("html_main") is True for block in web_blocks)
    for block in blocks:
        if block.id not in web_block_ids:
            output.append(block)
            continue
        role = block.attributes.get("html_role")
        tokens = block.attributes.get("html_selectors") or []
        token_text = " ".join(
            value for value in tokens if isinstance(value, str)
        ).casefold()
        reason = None
        if has_main and not block.attributes.get("html_main"):
            reason = "outside_main_content"
        elif step.remove_semantic_chrome and role in {
            "navigation",
            "banner",
            "contentinfo",
            "complementary",
            "dialog",
            "form",
        }:
            reason = "semantic_site_chrome"
        elif step.remove_cookie_banners and any(
            hint in token_text for hint in _COOKIE_HINTS
        ):
            reason = "cookie_or_consent_banner"
        elif (
            step.remove_repeated_site_chrome
            and _fingerprint(block.text) in repeated_fingerprints
        ):
            reason = "repeated_site_chrome"
        if reason:
            changes.append(
                TransformChange(block_id=block.id, action="removed", reason=reason)
            )
        else:
            output.append(block)
    return output, _audit(
        step.type,
        started,
        changes,
        metrics={
            "main_content_detected": has_main,
            "site_fingerprints_available": len(repeated_fingerprints),
        },
    )


def _validate(blocks, step):
    started = time.perf_counter_ns()
    characters = sum(len(block.text) for block in blocks)
    if characters < step.minimum_characters:
        raise IngestionStageError(
            "clean",
            "too_little_useful_content",
            "Cleaning left too little useful content for the saved minimum.",
        )
    if characters > step.maximum_characters:
        raise IngestionStageError(
            "clean",
            "too_much_useful_content",
            "Cleaned content exceeds the saved maximum character limit.",
        )
    return blocks, _audit(
        step.type,
        started,
        [],
        metrics={"useful_characters": characters, "validation_passed": True},
    )


def clean_structure_document(
    extracted: ExtractedDocumentV1,
    settings,
    *,
    extractor_version: str,
    configuration_hash: str,
    repeated_site_fingerprints: set[str] | None = None,
) -> CleanedDocumentV1:
    """Execute the saved ordered transform list and return a new immutable document."""

    from app.ingestion_content.canonical import document_hash

    blocks = list(extracted.blocks)
    audits = []
    protected = set(_PROTECTED_DEFAULT)
    repeated_site_fingerprints = repeated_site_fingerprints or set()
    for step in settings.steps:
        if not step.enabled:
            continue
        if step.type == "preserve_structure":
            started = time.perf_counter_ns()
            protected = set(step.block_types)
            audit = _audit(
                step.type,
                started,
                [],
                metrics={"protected_block_types": ",".join(step.block_types)},
            )
        elif step.type == "unicode_normalize":
            blocks, audit = _rewrite(
                blocks, step.type, lambda block: _unicode(block, step.form)
            )
            audit.metrics["form"] = step.form
        elif step.type == "remove_control_characters":
            blocks, audit = _rewrite(blocks, step.type, _controls)
        elif step.type == "reflow_pdf_lines":
            if extracted.media_type == "application/pdf":
                blocks, audit = _rewrite(
                    blocks,
                    step.type,
                    lambda block: _reflow(block, set(step.block_types)),
                    protected=protected,
                )
            else:
                audit = _audit(
                    step.type,
                    time.perf_counter_ns(),
                    [],
                    metrics={"applicable": False},
                )
        elif step.type == "dehyphenate":
            blocks, audit = _rewrite(
                blocks, step.type, _dehyphenate, protected=protected
            )
        elif step.type == "remove_repeated_headers_footers":
            blocks, audit = _remove_repeated_headers_footers(
                blocks, step, extracted.measurements.page_count, protected
            )
        elif step.type == "remove_empty_blocks":
            blocks, audit = _remove_empty(blocks, step, protected)
        elif step.type == "remove_literal_boilerplate":
            blocks, audit = _remove_literals(blocks, step, protected)
        elif step.type == "website_selectors":
            blocks, audit = _website_selectors(blocks, step)
        elif step.type == "website_main_content":
            blocks, audit = _website_main(blocks, step, repeated_site_fingerprints)
        elif step.type == "validate_useful_content":
            blocks, audit = _validate(blocks, step)
        else:  # pragma: no cover - strict schema makes this unreachable
            raise IngestionStageError(
                "clean",
                "unknown_transform",
                "The saved cleaning transform is unsupported.",
            )
        audits.append(audit)

    if settings.exact_content_deduplication:
        started = time.perf_counter_ns()
        seen: set[str] = set()
        output = []
        changes = []
        protected_retained = 0
        for block in blocks:
            digest = hashlib.sha256(block.text.encode("utf-8")).hexdigest()
            duplicate = digest in seen
            if duplicate and block.type not in protected:
                changes.append(
                    TransformChange(
                        block_id=block.id,
                        action="removed",
                        reason="exact_content_duplicate",
                    )
                )
            else:
                seen.add(digest)
                output.append(block)
                if duplicate and block.type in protected:
                    protected_retained += 1
        blocks = output
        audits.append(
            _audit(
                "exact_content_deduplication",
                started,
                changes,
                metrics={"protected_blocks_retained": protected_retained},
            )
        )

    blocks = [
        block.model_copy(update={"ordinal": index})
        for index, block in enumerate(blocks)
    ]
    characters = sum(len(block.text) for block in blocks)
    if characters < settings.minimum_text_chars:
        raise IngestionStageError(
            "clean",
            "too_little_useful_content",
            "Cleaning left too little useful content for the saved minimum.",
        )
    if characters > settings.maximum_text_chars:
        raise IngestionStageError(
            "clean",
            "too_much_useful_content",
            "Cleaned content exceeds the saved maximum character limit.",
        )
    page_numbers = [page.page_number for page in extracted.pages]
    measurements = extracted.measurements.model_copy(
        update={
            "character_count": characters,
            "block_count": len(blocks),
            "empty_block_count": sum(not block.text.strip() for block in blocks),
            "page_character_counts": [
                sum(len(block.text) for block in blocks if block.page_number == page)
                for page in page_numbers
            ],
            "page_block_counts": [
                sum(block.page_number == page for block in blocks)
                for page in page_numbers
            ],
        }
    )
    return CleanedDocumentV1(
        media_type=extracted.media_type,
        title=extracted.title,
        language=extracted.language,
        blocks=blocks,
        extractor_version=extractor_version,
        cleaner_version=STRUCTURE_CLEANER_VERSION,
        configuration_hash=configuration_hash,
        input_hash=document_hash(extracted.blocks),
        output_hash=document_hash(blocks),
        transforms=audits,
        measurements=measurements,
        findings=extracted.findings,
    )
