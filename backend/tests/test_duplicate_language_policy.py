import pytest

from app.ingestion_content.canonical import (
    CanonicalInputSegment,
    build_extracted_document,
)
from app.ingestion_content.duplicates import (
    DuplicateCandidate,
    classify_duplicates,
    simhash64,
    simhash_similarity,
)
from app.ingestion_content.language import apply_language_policy, detect_language
from app.ingestion_content.quality import measured_document
from app.schemas.ingestion import DuplicatePolicyV1, LanguagePolicyV1


def candidate(identity, text, *, kind="website", order=0, raw=None, cleaned=None):
    return DuplicateCandidate(
        identity=identity,
        source_kind=kind,
        raw_hash=raw or f"raw-{identity}",
        cleaned_hash=cleaned or f"clean-{identity}",
        text=text,
        stable_order=order,
    )


def document(*segments):
    value = build_extracted_document(
        [
            CanonicalInputSegment(text=text, page_number=index + 1)
            for index, text in enumerate(segments)
        ],
        media_type="text/plain",
        page_metadata={
            index + 1: {"character_count": len(text), "block_count": 1}
            for index, text in enumerate(segments)
        },
    )
    return measured_document(value, duration_ms=0)


def test_exact_and_normalized_duplicates_have_reproducible_counterparts():
    policy = DuplicatePolicyV1()
    values = [
        candidate("b", "Same policy text", order=1, raw="one"),
        candidate("a", " same   POLICY text ", order=0, raw="two"),
        candidate("c", "Different material", order=2),
    ]
    first = classify_duplicates(values, policy)
    second = classify_duplicates(list(reversed(values)), policy)
    assert first == second
    assert first["b"].outcome == "excluded"
    assert first["b"].retained_identity == "a"
    assert first["b"].method == "normalized_sections_sha256"
    assert first["c"].outcome == "retained"


def test_pinned_and_connector_priority_choose_canonical_without_mutation():
    policy = DuplicatePolicyV1(pinned_canonical_locations=["s3://bucket/copy"])
    values = [
        candidate("https://example.com/copy", "same", cleaned="same", kind="website"),
        candidate("s3://bucket/copy", "same", cleaned="same", kind="s3", order=10),
    ]
    decisions = classify_duplicates(values, policy)
    assert decisions["s3://bucket/copy"].outcome == "retained"
    assert decisions["https://example.com/copy"].retained_identity == "s3://bucket/copy"


def test_near_duplicate_threshold_is_saved_and_bounded():
    left = (
        "The policy applies to all employees and contractors in every regional office."
    )
    right = (
        "The policy applies to all employees and contractors in each regional office."
    )
    score = simhash_similarity(simhash64(left), simhash64(right))
    policy = DuplicatePolicyV1(near_duplicate=True, near_duplicate_threshold=score)
    decisions = classify_duplicates(
        [candidate("a", left), candidate("b", right, order=1)], policy
    )
    assert decisions["b"].method == "simhash64"
    assert decisions["b"].similarity >= policy.near_duplicate_threshold
    with pytest.raises(ValueError):
        DuplicatePolicyV1(near_duplicate_threshold=0.5)


def test_language_metadata_and_allowlist_decision_are_explicit():
    detected = detect_language("The guide is written in English and is for the team.")
    assert detected.language == "en"
    assert detected.model_version == "deterministic-script-v1"
    assert 0 <= detected.confidence <= 1

    excluded = apply_language_policy(
        document("The guide is written in English and is for the team."),
        LanguagePolicyV1(allowlist=["fr"], disallowed_action="exclude"),
    )
    assert excluded.language.language == "en"
    assert excluded.measurements.quality_decision == "exclude"
    assert any(value.code == "language_not_allowed" for value in excluded.findings)


def test_mixed_language_policy_uses_page_metadata_and_never_translates():
    value = apply_language_policy(
        document(
            "The first page is in English and is for the team.",
            "Это вторая страница документа на русском языке.",
        ),
        LanguagePolicyV1(mixed_language_action="warn", minimum_confidence=0),
    )
    assert value.language.mixed is True
    assert [page.language.language for page in value.pages] == ["en", "ru"]
    assert value.measurements.quality_decision == "warn"
    assert "Это" in value.blocks[1].text
    assert any(value.code == "mixed_languages" for value in value.findings)
