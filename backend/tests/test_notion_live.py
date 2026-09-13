"""Opt-in bounded Notion check; disabled without explicit workspace authorization."""

import os
from uuid import uuid4

import pytest

from app.connectors.notion import NotionConnector
from app.schemas.ingestion import NotionConfig


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_NOTION_AUTHORIZED") != "1",
    reason="Live Notion check requires explicit workspace authorization.",
)
def test_live_authorized_notion_page_discovery_and_fetch():
    token = os.environ.get("NOTION_LIVE_INTEGRATION_TOKEN")
    page_id = os.environ.get("NOTION_LIVE_PAGE_ID")
    assert token and page_id, "Set the authorized NOTION_LIVE_* variables."
    connector = NotionConnector(
        {"kind": "notion", "integration_token": token},
    )
    config = NotionConfig(
        kind="notion",
        connection_id=uuid4(),
        selection={"mode": "pages", "page_ids": [page_id]},
        max_pages=1,
        max_api_pages=20,
        max_blocks_per_page=100,
        max_block_depth=4,
        max_text_chars=50_000,
        request_timeout_seconds=5,
    )
    outcomes = connector.discover_all(config)
    assert len(outcomes) == 1 and outcomes[0].status == "included"
    item = connector.discover(config).items[0]
    artifact = connector.fetch(config, item)
    assert artifact.content and artifact.content_hash and artifact.segments
