"""Synthetic-only tests for deterministic sensitive-data transforms."""

import pytest

from app.ingestion_content.canonical import build_extracted_document, clean_document
from app.ingestion_content.processing import ExtractedSegment, cleaner_for_node
from app.ingestion_content.sensitive_data import (
    SensitiveDataDropError,
    apply_sensitive_data_policy,
)
from app.schemas.ingestion import CleanNodeV2, SensitiveDataPolicyV1


def _cleaned(text: str):
    extracted = build_extracted_document(
        [ExtractedSegment(text=text)],
        media_type="text/plain",
        title="Synthetic policy fixture",
    )
    settings = CleanNodeV2(id="clean", type="clean")
    return clean_document(
        extracted,
        settings,
        cleaner_for_node(settings),
        extractor_version="synthetic-v1",
        configuration_hash="a" * 64,
    )


def test_redacts_supported_entities_without_persisting_values():
    source = (
        "Email alex@example.test, phone +1 415-555-0132, IP 203.0.113.10, "
        "SSN 123-45-6789, card 4111 1111 1111 1111, "
        "and api_key=synthetic_token_123456789."
    )
    policy = SensitiveDataPolicyV1(enabled=True)
    result, audit = apply_sensitive_data_policy(_cleaned(source), policy)
    text = result.blocks[0].text
    assert text == (
        "Email [EMAIL], phone [PHONE], IP [IP_ADDRESS], SSN [GOVERNMENT_ID], "
        "card [PAYMENT_CARD], and api_key=[API_SECRET]."
    )
    assert audit is not None
    assert audit.metrics["finding_count"] == 6
    assert {item.entity_class for item in result.sensitive_findings} == {
        "email",
        "phone",
        "ip_address",
        "government_id",
        "payment_card",
        "api_secret",
    }
    encoded = str([item.model_dump() for item in result.sensitive_findings])
    for secret in (
        "alex@example.test",
        "415-555-0132",
        "203.0.113.10",
        "123-45-6789",
        "4111 1111 1111 1111",
        "synthetic_token_123456789",
    ):
        assert secret not in encoded


def test_false_positive_guards_and_overlap_prefer_validated_entities():
    source = (
        "Release 1.2.3.999, order 4111 1111 1111 1112, plain 123456789012, "
        "and date 2026-09-25 must stay unchanged."
    )
    result, audit = apply_sensitive_data_policy(
        _cleaned(source), SensitiveDataPolicyV1(enabled=True)
    )
    assert result.blocks[0].text == source
    assert result.sensitive_findings == []
    assert audit is not None and audit.metrics["finding_count"] == 0


def test_disabled_policy_preserves_historical_behavior():
    source = "alex@example.test"
    original = _cleaned(source)
    result, audit = apply_sensitive_data_policy(original, SensitiveDataPolicyV1())
    assert result == original
    assert audit is None


def test_cleaning_boundary_redacts_before_any_chunking_consumer():
    extracted = build_extracted_document(
        [ExtractedSegment(text="Evidence owner: alex@example.test")],
        media_type="text/plain",
        title="Synthetic policy fixture",
    )
    settings = CleanNodeV2(
        id="clean",
        type="clean",
        sensitive_data_policy=SensitiveDataPolicyV1(enabled=True),
    )
    result = clean_document(
        extracted,
        settings,
        cleaner_for_node(settings),
        extractor_version="synthetic-v1",
        configuration_hash="b" * 64,
    )
    assert result.blocks[0].text == "Evidence owner: [EMAIL]"
    assert result.output_hash != result.input_hash


def test_drop_document_raises_safe_location_only_decision():
    policy = SensitiveDataPolicyV1.model_validate(
        {
            "enabled": True,
            "rules": [
                {"entity_class": "email", "action": "drop_document"},
            ],
        }
    )
    with pytest.raises(SensitiveDataDropError) as raised:
        apply_sensitive_data_policy(_cleaned("alex@example.test"), policy)
    assert raised.value.code == "sensitive_data_drop_document"
    assert len(raised.value.findings) == 1
    assert raised.value.findings[0].entity_class == "email"
    assert "alex@example.test" not in str(raised.value.findings)


def test_policy_rejects_duplicate_rules_and_formats():
    with pytest.raises(ValueError, match="entity rules must be unique"):
        SensitiveDataPolicyV1.model_validate(
            {
                "rules": [
                    {"entity_class": "email"},
                    {"entity_class": "email"},
                ]
            }
        )
    with pytest.raises(ValueError, match="formats must be unique"):
        SensitiveDataPolicyV1(government_id_formats=["us_ssn", "us_ssn"])
