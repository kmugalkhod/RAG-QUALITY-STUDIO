"""Opt-in bounded S3 check; disabled unless an authorized bucket is explicit."""

import os
from uuid import uuid4

import pytest

from app.connectors.s3 import S3Connector
from app.schemas.ingestion import S3Config


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_S3_AUTHORIZED") != "1",
    reason="Live S3 check requires explicit authorization and bounded credentials.",
)
def test_live_authorized_s3_discovery_and_one_fetch():
    required = {
        name: os.environ.get(name)
        for name in (
            "S3_LIVE_ACCESS_KEY_ID",
            "S3_LIVE_SECRET_ACCESS_KEY",
            "S3_LIVE_REGION",
            "S3_LIVE_BUCKET",
            "S3_LIVE_PREFIX",
        )
    }
    assert all(required.values()), (
        "Set every S3_LIVE_* variable for the authorized scope."
    )
    connector = S3Connector(
        {
            "kind": "s3",
            "access_key_id": required["S3_LIVE_ACCESS_KEY_ID"],
            "secret_access_key": required["S3_LIVE_SECRET_ACCESS_KEY"],
            "session_token": os.environ.get("S3_LIVE_SESSION_TOKEN"),
        }
    )
    config = S3Config(
        kind="s3",
        connection_id=uuid4(),
        region=required["S3_LIVE_REGION"],
        bucket=required["S3_LIVE_BUCKET"],
        prefix=required["S3_LIVE_PREFIX"],
        expected_bucket_owner=os.environ.get("S3_LIVE_EXPECTED_BUCKET_OWNER"),
        allowed_file_types=["txt", "pdf"],
        max_objects=5,
        max_pages=1,
        max_object_bytes=1_000_000,
        max_total_bytes=1_000_000,
        request_timeout_seconds=5,
    )
    outcomes = connector.discover_all(config)
    included = next((item for item in outcomes if item.status == "included"), None)
    assert included is not None, (
        "Authorized prefix must contain a non-empty TXT or PDF."
    )
    page = connector.discover(config)
    item = next(
        value for value in page.items if value.external_id == included.external_id
    )
    artifact = connector.fetch(config, item)
    assert artifact.content and artifact.content_hash
