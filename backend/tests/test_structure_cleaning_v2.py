"""Spec 0012 Part D: structure-clean-v2."""

import pytest

from app.ingestion_content import (
    CanonicalInputSegment,
    build_extracted_document,
    clean_document,
    cleaner_for_node,
    processing_identity,
)
from app.ingestion_content.cleaning import (
    default_structure_steps,
    site_chrome_for,
    stored_site_chrome,
)
from app.ingestion_content.processing import IngestionStageError
from app.schemas.ingestion import CleanNodeV2


def settings(version, steps=None):
    return CleanNodeV2.model_validate(
        {
            "id": "clean",
            "type": "clean",
            "profile": "structure-aware-v1",
            "config_version": version,
            "steps": steps if steps is not None else default_structure_steps(),
        }
    )


def step(kind, **updates):
    value = next(item for item in default_structure_steps() if item["type"] == kind)
    return {**value, **updates}


def web_block(text, block_type="paragraph", key="main"):
    return CanonicalInputSegment(
        text=text,
        block_type=block_type,
        provider="website",
        external_id=key,
        attributes={
            "html_main": True,
            "html_role": "main",
            "html_selectors": ["main"],
        },
    )


def page(index, *repeated):
    return build_extracted_document(
        [
            *(
                web_block(text, block_type, f"{index}-{number}")
                for number, (text, block_type) in enumerate(repeated)
            ),
            web_block(
                f"Article {index} describes the ferry timetable in detail.",
                key=f"{index}-body",
            ),
        ],
        media_type="text/html",
    )


def run(version, pages):
    clean = settings(version)
    located = [
        (f"https://example.test/{index}", doc) for index, doc in enumerate(pages)
    ]
    chrome = site_chrome_for(clean, located, 0.6)
    outputs = [
        clean_document(
            document,
            clean,
            cleaner_for_node(clean),
            extractor_version="html-main-v2",
            configuration_hash="b" * 64,
            repeated_site_fingerprints=chrome,
            document_location=location,
        )
        for location, document in located
    ]
    return (
        chrome,
        [[block.text for block in output.blocks] for output in outputs],
        outputs,
    )


REPEATED = [
    ("Subscribe to our newsletter", "paragraph"),
    ("Fare | Adult | 4.50", "table"),
    ("Children travel free", "list_item"),
]


def test_v1_removes_every_copy_of_repeated_blocks_including_protected_ones():
    _, texts, _ = run(
        "structure-clean-v1", [page(index, *REPEATED) for index in range(3)]
    )

    assert texts == [
        [f"Article {index} describes the ferry timetable in detail."]
        for index in range(3)
    ]


def test_v2_keeps_protected_blocks_and_the_first_pages_copy():
    chrome, texts, outputs = run(
        "structure-clean-v2", [page(index, *REPEATED) for index in range(3)]
    )

    assert set(chrome.values()) == {"https://example.test/0"}
    body = "describes the ferry timetable in detail."
    assert texts[0] == [
        "Subscribe to our newsletter",
        "Fare | Adult | 4.50",
        "Children travel free",
        f"Article 0 {body}",
    ]
    for index in (1, 2):
        assert texts[index] == [
            "Fare | Adult | 4.50",
            "Children travel free",
            f"Article {index} {body}",
        ]
    audit = next(
        a for a in outputs[1].transforms if a.transform == "website_main_content"
    )
    assert audit.metrics["repeated_blocks_kept"] == 2
    assert {a.version for a in outputs[1].transforms} == {"structure-clean-v2"}
    assert outputs[1].cleaner_version == "structure-clean-v2"


def test_v2_matches_repeats_after_normalization():
    # A soft hyphen in every copy hid the repeat from v1, which fingerprints the
    # extracted text but compares it after control characters are removed.
    soft = [("Sub­scribe to our newsletter", "paragraph")]
    _, v1, _ = run("structure-clean-v1", [page(index, *soft) for index in range(3)])
    _, v2, _ = run("structure-clean-v2", [page(index, *soft) for index in range(3)])

    assert all("Subscribe to our newsletter" in texts for texts in v1)
    assert "Subscribe to our newsletter" in v2[0]
    assert all("Subscribe to our newsletter" not in texts for texts in v2[1:])


def test_saved_chrome_round_trips_through_run_state():
    chrome, _, _ = run(
        "structure-clean-v2", [page(index, *REPEATED) for index in range(3)]
    )
    assert stored_site_chrome(chrome) == chrome
    v1_chrome, _, _ = run(
        "structure-clean-v1", [page(index, *REPEATED) for index in range(3)]
    )
    assert stored_site_chrome(v1_chrome) == sorted(v1_chrome)


@pytest.mark.parametrize(
    ("minimum", "maximum", "text", "message"),
    [
        (
            20,
            2_000_000,
            "short",
            "Cleaning left 5 characters of useful text; the minimum is 20.",
        ),
        (1, 4, "short", "Cleaning left 5 characters of useful text; the maximum is 4."),
    ],
)
def test_v2_checks_length_once_with_the_measured_number(
    minimum, maximum, text, message
):
    clean = settings(
        "structure-clean-v2",
        [
            step(
                "validate_useful_content",
                minimum_characters=minimum,
                maximum_characters=maximum,
            )
        ],
    )
    extracted = build_extracted_document(
        [CanonicalInputSegment(text=text, block_type="paragraph")],
        media_type="text/plain",
    )
    with pytest.raises(IngestionStageError) as raised:
        clean_document(
            extracted,
            clean,
            cleaner_for_node(clean),
            extractor_version="test-extractor-v1",
            configuration_hash="a" * 64,
        )
    assert raised.value.stage == "clean"
    assert raised.value.message == message
    # The service-level check no longer repeats it.
    assert cleaner_for_node(clean).length_violation(len(text), clean) is None


def test_v2_has_its_own_identity_and_v1_keeps_its_own():
    v1 = cleaner_for_node(settings("structure-clean-v1"))
    v2 = cleaner_for_node(settings("structure-clean-v2"))
    assert (v1.version, v2.version) == ("structure-clean-v1", "structure-clean-v2")

    def identity(cleaner):
        return processing_identity(
            schema_version=2,
            extractor_version="layout-ocr-v5",
            cleaner_version=cleaner.version,
            chunker_version="section-token-v2",
            extract={},
            clean={},
            chunk={},
        )[1]

    assert identity(v1) != identity(v2)
