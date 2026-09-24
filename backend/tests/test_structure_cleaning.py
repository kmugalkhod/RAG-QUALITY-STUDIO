from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    clean_document,
    cleaner_for_node,
    processing_identity,
)
from app.ingestion_content.cleaning import (
    default_structure_steps,
    website_text_fingerprints,
)
from app.ingestion_content.contracts import BoundingBox
from app.ingestion_content.processing import IngestionStageError
from app.schemas.ingestion import CleanNodeV2
from app.pipelines.web_content import extract_canonical_sections
from app.connectors.website import WebsiteArtifact
from app.services.website_ingestion import canonical_extracted_document


def settings(steps=None, **updates):
    values = {
        "id": "clean",
        "type": "clean",
        "profile": "structure-aware-v1",
        "config_version": "structure-clean-v1",
        "steps": steps if steps is not None else default_structure_steps(),
    }
    values.update(updates)
    return CleanNodeV2.model_validate(values)


def cleaned(segments, clean=None, media_type="application/pdf", pages=None):
    extracted = build_extracted_document(
        segments,
        media_type=media_type,
        page_metadata=pages,
    )
    clean = clean or settings()
    return clean_document(
        extracted,
        clean,
        cleaner_for_node(clean),
        extractor_version="test-extractor-v1",
        configuration_hash="a" * 64,
    )


def step(kind, **updates):
    value = next(item for item in default_structure_steps() if item["type"] == kind)
    return {**value, **updates}


def test_unicode_controls_reflow_and_dehyphenation_are_ordered_and_attributed():
    result = cleaned(
        [
            CanonicalInputSegment(
                text="Cafe\u0301\x00 first\nline inter-\nnational",
                page_number=1,
                block_type="paragraph",
            ),
            CanonicalInputSegment(
                text="code-\nboundary",
                page_number=1,
                block_type="code",
            ),
        ],
        pages={1: {}},
    )
    assert result.blocks[0].text == "Café first line international"
    assert result.blocks[1].text == "code-\nboundary"
    assert result.blocks[0].attributes["cleaning"]["parent_block_ids"]
    audits = {audit.transform: audit for audit in result.transforms}
    assert audits["unicode_normalize"].changed_blocks == 1
    assert audits["remove_control_characters"].metrics["change_count"] == 1
    assert audits["reflow_pdf_lines"].metrics["change_count"] == 1
    assert audits["dehyphenate"].metrics["change_count"] == 1


def test_nfkc_is_explicit_and_can_change_compatibility_characters():
    nfc = cleaned(
        [CanonicalInputSegment(text="①", block_type="paragraph")],
        settings(
            [step("unicode_normalize", form="NFC"), step("validate_useful_content")]
        ),
        media_type="text/plain",
    )
    nfkc = cleaned(
        [CanonicalInputSegment(text="①", block_type="paragraph")],
        settings(
            [step("unicode_normalize", form="NFKC"), step("validate_useful_content")]
        ),
        media_type="text/plain",
    )
    assert nfc.blocks[0].text == "①"
    assert nfkc.blocks[0].text == "1"


def test_repeated_margin_removal_is_positional_and_preserves_body_match():
    segments = []
    for page in range(1, 5):
        segments.extend(
            [
                CanonicalInputSegment(
                    text="Quarterly report",
                    page_number=page,
                    block_type="paragraph",
                    bounding_box=BoundingBox(
                        left=0.1, top=0.01, right=0.9, bottom=0.05
                    ),
                ),
                CanonicalInputSegment(
                    text="Quarterly report" if page == 1 else f"Body {page}",
                    page_number=page,
                    block_type="paragraph",
                    bounding_box=BoundingBox(left=0.1, top=0.3, right=0.9, bottom=0.6),
                ),
            ]
        )
    result = cleaned(
        segments,
        settings(
            [
                step("preserve_structure"),
                step("remove_repeated_headers_footers"),
                step("validate_useful_content"),
            ]
        ),
        pages={page: {} for page in range(1, 5)},
    )
    assert [block.text for block in result.blocks] == [
        "Quarterly report",
        "Body 2",
        "Body 3",
        "Body 4",
    ]
    audit = result.transforms[1]
    assert audit.removed_blocks == 4
    assert audit.metrics["fingerprints_removed"] == 1


def test_literal_and_empty_removal_respect_protected_block_types():
    clean = settings(
        [
            step("preserve_structure", block_types=["table", "code"]),
            {
                "id": "literal",
                "type": "remove_literal_boilerplate",
                "enabled": True,
                "values": ["REMOVE"],
                "block_types": ["paragraph", "table"],
            },
            step("remove_empty_blocks", minimum_characters=2),
            step("validate_useful_content"),
        ]
    )
    result = cleaned(
        [
            CanonicalInputSegment(text="REMOVE useful", block_type="paragraph"),
            CanonicalInputSegment(text="REMOVE", block_type="table"),
            CanonicalInputSegment(text="x", block_type="code"),
            CanonicalInputSegment(text="x", block_type="paragraph"),
        ],
        clean,
        media_type="text/plain",
    )
    assert [block.text for block in result.blocks] == [" useful", "REMOVE", "x"]
    assert result.transforms[2].metrics["protected_blocks_retained"] == 1


def test_website_selector_main_content_and_cross_page_fingerprints():
    def web_doc(unique):
        return build_extracted_document(
            [
                CanonicalInputSegment(
                    text="Shared navigation",
                    block_type="unknown",
                    provider="website",
                    external_id=f"{unique}-nav",
                    attributes={
                        "html_main": False,
                        "html_role": "navigation",
                        "html_selectors": ["nav", ".global-nav", "[role=navigation]"],
                    },
                ),
                CanonicalInputSegment(
                    text=unique,
                    block_type="paragraph",
                    provider="website",
                    external_id=f"{unique}-main",
                    attributes={
                        "html_main": True,
                        "html_role": "main",
                        "html_selectors": ["main", ".content", "[role=main]"],
                    },
                ),
            ],
            media_type="text/html",
        )

    docs = [web_doc(f"Article {index}") for index in range(3)]
    fingerprints = website_text_fingerprints(docs, 0.6)
    assert fingerprints == {"shared navigation"}
    clean = settings(
        [
            {
                "id": "selectors",
                "type": "website_selectors",
                "enabled": True,
                "include": ["main"],
                "exclude": [".cookie-banner"],
            },
            step("website_main_content"),
            step("validate_useful_content"),
        ]
    )
    result = clean_document(
        docs[0],
        clean,
        cleaner_for_node(clean),
        extractor_version="html-main-v2",
        configuration_hash="b" * 64,
        repeated_site_fingerprints=fingerprints,
    )
    assert [block.text for block in result.blocks] == ["Article 0"]
    assert result.transforms[0].removed_blocks == 1


def test_structured_html_extraction_is_non_executing_and_retains_safe_selector_metadata():
    sections = extract_canonical_sections(
        b"<nav class='global-nav'>Navigation</nav><main id='content'><h1>Guide</h1>"
        b"<p>Useful <script>steal()</script>text</p>"
        b"<div class='cookie-banner' role='dialog'>Cookies</div></main>"
    )
    assert "steal" not in " ".join(section.text for section in sections)
    assert any(
        section.block_type == "heading" and section.text == "Guide"
        for section in sections
    )
    useful = next(section for section in sections if section.text == "Useful text")
    assert useful.attributes["html_main"] is True
    assert "main" in useful.attributes["html_selectors"]
    assert "#content" in useful.attributes["html_selectors"]
    cookie = next(section for section in sections if section.text == "Cookies")
    assert ".cookie-banner" in cookie.attributes["html_selectors"]
    assert cookie.attributes["html_role"] == "dialog"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda values: values["steps"].reverse(),
        lambda values: values["steps"].append(deepcopy(values["steps"][0])),
        lambda values: values["steps"].append(
            {
                "id": "unsafe-selector",
                "type": "website_selectors",
                "enabled": True,
                "include": ["main > script"],
                "exclude": [],
            }
        ),
    ],
)
def test_transform_order_ids_and_selector_subset_are_validated(mutate):
    values = {
        "id": "clean",
        "type": "clean",
        "profile": "structure-aware-v1",
        "config_version": "structure-clean-v1",
        "steps": default_structure_steps(),
    }
    mutate(values)
    with pytest.raises(ValidationError):
        CleanNodeV2.model_validate(values)


def test_ordered_configuration_hash_and_output_are_deterministic():
    clean = settings()
    first_identity = processing_identity(
        schema_version=2,
        extractor_version="extract-v1",
        cleaner_version="structure-clean-v1",
        chunker_version="character-window-v1",
        extract={},
        clean=clean.model_dump(mode="json", exclude={"id", "type"}),
        chunk={"size": 100, "overlap": 10},
    )
    second_identity = processing_identity(
        schema_version=2,
        extractor_version="extract-v1",
        cleaner_version="structure-clean-v1",
        chunker_version="character-window-v1",
        extract={},
        clean=clean.model_dump(mode="json", exclude={"id", "type"}),
        chunk={"size": 100, "overlap": 10},
    )
    assert first_identity == second_identity
    segments = [CanonicalInputSegment(text="Stable\ntext", block_type="paragraph")]
    first = cleaned(segments, clean, media_type="text/plain")
    second = cleaned(segments, clean, media_type="text/plain")
    assert first.blocks == second.blocks
    assert first.output_hash == second.output_hash
    assert [
        audit.model_dump(exclude={"duration_ms"}) for audit in first.transforms
    ] == [audit.model_dump(exclude={"duration_ms"}) for audit in second.transforms]


def test_useful_content_validation_fails_with_safe_stage_error():
    clean = settings([step("validate_useful_content", minimum_characters=20)])
    with pytest.raises(
        IngestionStageError, match="too little useful content"
    ) as raised:
        cleaned(
            [CanonicalInputSegment(text="short", block_type="paragraph")],
            clean,
            media_type="text/plain",
        )
    assert raised.value.stage == "clean"
    assert raised.value.code == "too_little_useful_content"


def test_reviewed_cleaning_corpus_meets_boilerplate_precision_and_recall():
    manifest = json.loads(
        (
            Path(__file__).parent / "fixtures" / "cleaning_corpus" / "manifest.json"
        ).read_text()
    )
    clean = settings()
    expected_removed: set[str] = set()
    actual_removed: set[str] = set()
    reviewed_retained: set[str] = set()

    pdf = manifest["pdf_margin_case"]
    segments = []
    for page, body in enumerate(pdf["body"], 1):
        for label, value, block_type, box in (
            (
                "header",
                pdf["header"],
                "paragraph",
                BoundingBox(left=0.1, top=0.01, right=0.9, bottom=0.05),
            ),
            (
                "body",
                body,
                "paragraph",
                BoundingBox(left=0.1, top=0.25, right=0.9, bottom=0.6),
            ),
            (
                "footnote",
                pdf["protected_footnote"],
                "footnote",
                BoundingBox(left=0.1, top=0.8, right=0.9, bottom=0.86),
            ),
            (
                "footer",
                pdf["footer"],
                "paragraph",
                BoundingBox(left=0.1, top=0.94, right=0.9, bottom=0.98),
            ),
        ):
            segments.append(
                CanonicalInputSegment(
                    text=value,
                    page_number=page,
                    block_type=block_type,
                    bounding_box=box,
                    attributes={"review_label": f"pdf-{page}-{label}"},
                )
            )
    extracted = build_extracted_document(
        segments,
        media_type="application/pdf",
        page_metadata={page: {} for page in range(1, pdf["pages"] + 1)},
    )
    result = clean_document(
        extracted,
        clean,
        cleaner_for_node(clean),
        extractor_version="corpus-pdf-v1",
        configuration_hash="c" * 64,
    )
    retained_ids = {block.id for block in result.blocks}
    for block in extracted.blocks:
        label = block.attributes["review_label"]
        if label.endswith(("-header", "-footer")):
            expected_removed.add(label)
        else:
            reviewed_retained.add(label)
        if block.id not in retained_ids:
            actual_removed.add(label)

    artifacts = [
        WebsiteArtifact(
            canonical_location=value["url"],
            content=value["html"].encode(),
            media_type="text/html",
            etag=None,
            last_modified=None,
            validator_unchanged=False,
            depth=0,
        )
        for value in manifest["website_cases"]
    ]
    documents = [
        canonical_extracted_document(artifact, clean) for artifact in artifacts
    ]
    fingerprints = website_text_fingerprints(documents)
    for number, document in enumerate(documents):
        output = clean_document(
            document,
            clean,
            cleaner_for_node(clean),
            extractor_version="corpus-html-v1",
            configuration_hash="d" * 64,
            repeated_site_fingerprints=fingerprints,
        )
        retained_ids = {block.id for block in output.blocks}
        for block in document.blocks:
            label = f"web-{number}-{block.ordinal}"
            if block.attributes.get("html_main"):
                reviewed_retained.add(label)
            else:
                expected_removed.add(label)
            if block.id not in retained_ids:
                actual_removed.add(label)

    true_positive = len(actual_removed & expected_removed)
    precision = true_positive / len(actual_removed)
    recall = true_positive / len(expected_removed)
    assert not (actual_removed & reviewed_retained)
    assert precision >= 0.99
    assert recall >= 0.90
    assert precision == recall == 1
