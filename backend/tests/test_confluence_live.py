"""Opt-in bounded Confluence check; disabled without explicit site authorization."""

import os
from uuid import uuid4

import pytest

from app.connectors.confluence import ConfluenceConnector
from app.schemas.ingestion import ConfluenceConfig


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_CONFLUENCE_AUTHORIZED") != "1",
    reason="Live Confluence check requires explicit site authorization.",
)
def test_live_authorized_confluence_page_discovery_and_fetch():
    site = os.environ.get("CONFLUENCE_LIVE_SITE_URL")
    email = os.environ.get("CONFLUENCE_LIVE_EMAIL")
    token = os.environ.get("CONFLUENCE_LIVE_API_TOKEN")
    page_id = os.environ.get("CONFLUENCE_LIVE_PAGE_ID")
    assert site and email and token and page_id, (
        "Set the authorized CONFLUENCE_LIVE_* variables."
    )
    connector = ConfluenceConnector(
        {"kind": "confluence", "site_url": site, "email": email, "api_token": token}
    )
    config = ConfluenceConfig(
        kind="confluence",
        connection_id=uuid4(),
        selection={"mode": "pages", "page_ids": [page_id]},
        max_pages=1,
        max_api_pages=4,
        max_response_bytes=2 * 1024 * 1024,
        max_text_chars=50_000,
        request_timeout_seconds=5,
    )
    outcomes = connector.discover_all(config)
    assert len(outcomes) == 1 and outcomes[0].status == "included"
    item = connector.discover(config).items[0]
    artifact = connector.fetch(config, item)
    assert artifact.content and artifact.content_hash and artifact.segments
