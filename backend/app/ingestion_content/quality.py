"""Versioned, observable extraction-quality policy evaluation."""

from __future__ import annotations

from collections import Counter
from statistics import median
import unicodedata

from app.ingestion_content.contracts import (
    DocumentMeasurements,
    ExtractedDocumentV1,
    QualityFinding,
)


def quality_policy_settings(policy) -> dict:
    """Return one bounded runtime policy for typed and historical saved configs."""

    policy_id = policy if isinstance(policy, str) else policy.id
    if isinstance(policy, str):
        strict = policy_id == "strict-v1"
        return {
            "id": policy_id,
            "maximum_empty_page_ratio": 0 if strict else 0.20,
            "maximum_replacement_character_ratio": 0.001 if strict else 0.01,
            "maximum_control_character_ratio": 0 if strict else 0.001,
            "minimum_ocr_confidence": 70 if strict else 50,
            "fail_on_suspicious_reading_order": strict,
            "fail_on_malformed_tables": policy_id != "warn-v1",
            # Historical versions published warnings; preserve that behavior exactly.
            "warning_action": "publish",
            "failed_item_action": "exclude" if policy_id == "warn-v1" else "fail",
            "legacy": True,
        }
    thresholds = policy.thresholds
    return {
        "id": policy_id,
        "maximum_empty_page_ratio": thresholds.maximum_empty_page_ratio,
        "maximum_replacement_character_ratio": (
            thresholds.maximum_replacement_character_ratio
        ),
        "maximum_control_character_ratio": thresholds.maximum_control_character_ratio,
        "minimum_ocr_confidence": thresholds.minimum_ocr_confidence,
        "fail_on_suspicious_reading_order": (
            thresholds.fail_on_suspicious_reading_order
        ),
        "fail_on_malformed_tables": thresholds.fail_on_malformed_tables,
        "warning_action": policy.warning_action,
        "failed_item_action": policy.failed_item_action,
        "legacy": False,
    }


def quality_allows_publication(policy, decision: str) -> bool:
    settings = quality_policy_settings(policy)
    return decision == "pass" or (
        decision == "warn" and settings["warning_action"] == "publish"
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def measured_document(
    document: ExtractedDocumentV1,
    *,
    duration_ms: int,
    table_count: int = 0,
    malformed_table_count: int = 0,
    suspicious_reading_order_count: int = 0,
) -> ExtractedDocumentV1:
    """Calculate bounded document/page measurements without retaining source excerpts."""

    texts = [block.text for block in document.blocks]
    combined = "".join(texts)
    lines = [
        line.strip() for value in texts for line in value.splitlines() if line.strip()
    ]
    repeated = sum(count - 1 for count in Counter(lines).values() if count > 1)
    replacements = combined.count("\ufffd")
    controls = sum(
        1
        for value in combined
        if unicodedata.category(value) == "Cc" and value not in "\n\r\t"
    )
    page_character_counts = [page.character_count for page in document.pages]
    page_block_counts = [page.block_count for page in document.pages]
    confidences = sorted(
        page.ocr_confidence
        for page in document.pages
        if page.ocr_confidence is not None
    )
    p05_index = max(0, int((len(confidences) - 1) * 0.05)) if confidences else 0
    measurements = DocumentMeasurements(
        character_count=len(combined),
        block_count=len(document.blocks),
        page_count=len(document.pages),
        empty_block_count=sum(not value.strip() for value in texts),
        page_character_counts=page_character_counts,
        page_block_counts=page_block_counts,
        native_page_count=sum(page.origin == "native" for page in document.pages),
        layout_page_count=sum(page.origin == "layout" for page in document.pages),
        ocr_page_count=sum(page.origin == "ocr" for page in document.pages),
        empty_page_count=sum(count == 0 for count in page_character_counts),
        replacement_character_ratio=_ratio(replacements, len(combined)),
        control_character_ratio=_ratio(controls, len(combined)),
        repeated_line_ratio=_ratio(repeated, len(lines)),
        suspicious_reading_order_count=suspicious_reading_order_count,
        table_count=table_count,
        malformed_table_count=malformed_table_count,
        ocr_confidence_median=median(confidences) if confidences else None,
        ocr_confidence_p05=confidences[p05_index] if confidences else None,
        extraction_duration_ms=max(0, duration_ms),
        resource_category=(
            "bounded-cpu"
            if any(page.origin in {"layout", "ocr"} for page in document.pages)
            else "native"
        ),
        fallback_path=[
            f"page-{page.page_number}:{page.origin}"
            + (f":{page.fallback_reason}" if page.fallback_reason else "")
            for page in document.pages
        ],
    )
    return document.model_copy(update={"measurements": measurements})


def evaluate_quality(
    document: ExtractedDocumentV1,
    policy,
) -> ExtractedDocumentV1:
    """Map measurements to a saved decision and safe remediation findings."""

    measurements = document.measurements
    findings = list(document.findings)
    page_count = max(1, measurements.page_count)
    empty_ratio = measurements.empty_page_count / page_count

    def add(
        code: str,
        severity: str,
        message: str,
        *,
        pages: list[int] | None = None,
        remediation: str | None = None,
        count: int = 1,
    ):
        findings.append(
            QualityFinding(
                code=code,
                severity=severity,
                message=message,
                count=max(1, count),
                page_numbers=pages or [],
                remediation=remediation,
            )
        )

    if not document.blocks or measurements.character_count == 0:
        add(
            "no_extractable_text",
            "error",
            "No extractable text remained after bounded extraction.",
            remediation="Enable automatic OCR or inspect the source document.",
        )

    empty_pages = [
        page.page_number for page in document.pages if page.character_count == 0
    ]
    policy_settings = quality_policy_settings(policy)
    warn_only = policy_settings["id"] == "warn-v1"
    if empty_pages:
        severity = (
            "error"
            if not warn_only
            and empty_ratio > policy_settings["maximum_empty_page_ratio"]
            else "warning"
        )
        add(
            "empty_pages",
            severity,
            "One or more pages produced no usable text.",
            pages=empty_pages[:100],
            remediation="Enable automatic OCR or review the affected pages.",
            count=len(empty_pages),
        )
    if (
        measurements.replacement_character_ratio
        > policy_settings["maximum_replacement_character_ratio"]
    ):
        add(
            "replacement_character_ratio_high",
            "warning" if warn_only else "error",
            "Replacement-character frequency exceeded the saved quality threshold.",
            remediation="Use Layout-aware extraction or inspect font encoding.",
        )
    elif measurements.replacement_character_ratio > 0.001:
        add(
            "replacement_characters_present",
            "warning",
            "Replacement characters were observed in extracted text.",
            remediation="Inspect the affected extraction before publication.",
        )
    if (
        measurements.control_character_ratio
        > policy_settings["maximum_control_character_ratio"]
    ):
        add(
            "control_character_ratio_high",
            "warning" if warn_only else "error",
            "Unsupported control-character frequency exceeded the saved threshold.",
            remediation="Inspect document encoding before publication.",
        )
    if measurements.suspicious_reading_order_count:
        add(
            "suspicious_reading_order",
            "error"
            if policy_settings["fail_on_suspicious_reading_order"] and not warn_only
            else "warning",
            "The layout adapter detected ambiguous reading order.",
            remediation="Inspect block order or select Layout-aware extraction.",
            count=measurements.suspicious_reading_order_count,
        )
    if measurements.malformed_table_count:
        add(
            "malformed_tables",
            "error"
            if policy_settings["fail_on_malformed_tables"] and not warn_only
            else "warning",
            "One or more tables exceeded supported structural bounds.",
            remediation="Inspect the table rendering before publication.",
            count=measurements.malformed_table_count,
        )
    if measurements.ocr_confidence_p05 is not None:
        limit = policy_settings["minimum_ocr_confidence"]
        if measurements.ocr_confidence_p05 < limit:
            add(
                "ocr_confidence_low",
                "warning" if warn_only else "error",
                "OCR engine confidence fell below the saved quality threshold.",
                remediation="Check OCR languages, rotation and scan resolution.",
            )
        elif measurements.ocr_confidence_p05 < 70:
            add(
                "ocr_confidence_bounded",
                "warning",
                "Some OCR text has bounded low engine confidence.",
                remediation="Review OCR-marked blocks before publication.",
            )

    has_errors = any(item.severity == "error" for item in findings)
    has_warnings = any(item.severity == "warning" for item in findings)
    decision = "pass"
    if has_errors:
        decision = (
            "exclude"
            if policy_settings["legacy"]
            and (empty_ratio >= 0.75 or not document.blocks)
            else policy_settings["failed_item_action"]
        )
    elif has_warnings:
        decision = "warn"
    return document.model_copy(
        update={
            "findings": findings,
            "measurements": measurements.model_copy(
                update={"quality_decision": decision}
            ),
        }
    )
