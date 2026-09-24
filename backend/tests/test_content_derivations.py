from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.connectors.base import DiscoveredItem
from app.connectors.confluence import (
    ConfluenceArtifact,
    ConfluenceSegment,
)
from app.connectors.notion import NotionArtifact, NotionSegment
from app.connectors.website import WebsiteArtifact
from app.ingestion_content import (
    CanonicalInputSegment,
    CleanSemantics,
    DeterministicCleaner,
    build_extracted_document,
    chunk_cleaned_document,
    clean_document,
)
from app.ingestion_content.contracts import BoundingBox, CanonicalBlock
from app.schemas.ingestion import ChunkNodeV2, CleanNodeV2
from app.services.confluence_ingestion import _canonical_chunks as confluence_chunks
from app.services.notion_ingestion import _canonical_chunks as notion_chunks
from app.services.s3_ingestion import _canonical_chunks as s3_chunks
from app.services.website_ingestion import _canonical_chunks as website_chunks


class Clean:
    normalize_whitespace = True
    repeated_boilerplate = []
    minimum_text_chars = 1
    maximum_text_chars = 1_000
    exact_content_deduplication = True


class Chunk:
    size = 6
    overlap = 2


def test_canonical_document_and_lineage_are_deterministic():
    segments = [
        CanonicalInputSegment(
            text="  first block  ",
            page_number=1,
            block_type="paragraph",
            heading_path=("One",),
        ),
        CanonicalInputSegment(
            text="second block",
            page_number=2,
            block_type="paragraph",
        ),
    ]
    first = build_extracted_document(segments, media_type="text/plain")
    second = build_extracted_document(segments, media_type="text/plain")
    assert first == second
    assert [page.page_number for page in first.pages] == [1, 2]

    cleaned = clean_document(
        first,
        Clean(),
        DeterministicCleaner(CleanSemantics.STANDARD_V1),
        extractor_version="test-v1",
        configuration_hash="a" * 64,
    )
    chunking = chunk_cleaned_document(cleaned, Chunk())
    assert chunking.chunks[0].text == "first "
    assert chunking.spans[0][0].block_id == cleaned.blocks[0].id
    assert chunking.spans[0][0].block_start_char == 0
    assert chunking.spans[0][0].chunk_end_char == 6


def test_canonical_contracts_reject_malformed_geometry_and_metadata():
    with pytest.raises(ValidationError):
        BoundingBox(left=0.8, top=0.1, right=0.2, bottom=0.9)
    with pytest.raises(ValidationError):
        CanonicalBlock(
            id="a" * 16,
            ordinal=0,
            type="paragraph",
            text="value",
            source_span={
                "kind": "artifact_text",
                "start_char": 5,
                "end_char": 2,
            },
            attributes={"payload": "x" * 20_000},
        )


def test_all_v2_connectors_emit_canonical_ir_and_exact_lineage(tmp_path):
    clean = CleanNodeV2(id="clean", type="clean")
    chunk = ChunkNodeV2(id="chunk", type="chunk", size=100, overlap=10)
    current = datetime.now(UTC)
    content = "Canonical connector content. " * 12
    second_content = "A different canonical section. " * 12
    website = website_chunks(
        WebsiteArtifact(
            canonical_location="https://example.com/guide",
            content=(
                f"<main><h1>Guide</h1><p>{content}</p><p>{second_content}</p></main>"
            ).encode(),
            media_type="text/html",
            etag=None,
            last_modified=None,
            validator_unchanged=False,
            depth=0,
        ),
        chunk,
        clean,
        "a" * 64,
    )

    notion_item = DiscoveredItem(
        external_id="notion-page",
        display_name="Notion guide",
        canonical_location="https://notion.so/notion-page",
        media_type="text/plain",
    )
    notion = notion_chunks(
        NotionArtifact(
            item=notion_item,
            content=content.encode(),
            content_hash="b" * 64,
            segments=(
                NotionSegment(
                    text=content,
                    block_id="notion-block",
                    block_type="paragraph",
                    depth=0,
                    section_path=("Guide",),
                ),
            ),
            fetched_at=current,
        ),
        chunk,
        clean,
        "a" * 64,
    )

    confluence_item = notion_item.model_copy(
        update={
            "external_id": "confluence-page",
            "display_name": "Confluence guide",
            "canonical_location": "https://example.atlassian.net/wiki/guide",
        }
    )
    confluence = confluence_chunks(
        ConfluenceArtifact(
            item=confluence_item,
            content=content.encode(),
            content_hash="c" * 64,
            segments=(
                ConfluenceSegment(
                    text=content,
                    element="p",
                    ordinal=0,
                    section_path=("Guide",),
                ),
            ),
            fetched_at=current,
        ),
        chunk,
        clean,
        "a" * 64,
    )

    path = tmp_path / "guide.txt"
    path.write_text(content)
    s3 = s3_chunks(
        path,
        "text/plain",
        "guides/guide.txt",
        "guide.txt",
        chunk,
        clean,
        "a" * 64,
    )

    for prepared in (website, notion, confluence, s3):
        assert prepared.extracted is not None
        assert prepared.cleaned is not None
        assert prepared.chunks
        assert prepared.spans
        assert set(prepared.spans) == {value["ordinal"] for value in prepared.chunks}
        assert all(prepared.spans[value["ordinal"]] for value in prepared.chunks)
    assert any(len(spans) > 1 for spans in website.spans.values())
