"""Deterministic connector doubles shared by ingestion phase tests."""

from datetime import datetime, timezone
from hashlib import sha256

from app.connectors.base import (
    ChangedFetch,
    ConnectionCheck,
    DiscoveredItem,
    DiscoveryPage,
    FetchResult,
    UnchangedFetch,
)


class DeterministicConnector:
    kind = "fixture"
    config_version = "1"

    def __init__(self, items: dict[str, bytes]):
        self.items = dict(items)
        self.now = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

    def validate(self, config, connection):
        if config != {"scope": "all"} or connection is not None:
            raise ValueError("Invalid deterministic fixture configuration.")

    def test_connection(self, connection):
        return ConnectionCheck(status="available", message="Fixture is available.")

    def discover(self, config, cursor=None):
        self.validate(config, None)
        items = [
            DiscoveredItem(
                external_id=key,
                display_name=key,
                canonical_location=f"fixture://{key}",
                media_type="text/plain",
                provider_revision=sha256(value).hexdigest(),
            )
            for key, value in sorted(self.items.items())
        ]
        return DiscoveryPage(items=items, next_cursor=None)

    def fetch(self, item, prior_revision=None) -> FetchResult:
        content = self.items[item.external_id]
        digest = sha256(content).hexdigest()
        if prior_revision == digest:
            return UnchangedFetch(
                status="unchanged",
                item=item,
                prior_content_hash=digest,
                checked_at=self.now,
            )
        return ChangedFetch(
            status="changed",
            item=item,
            content=content,
            content_hash=digest,
            fetched_at=self.now,
        )
