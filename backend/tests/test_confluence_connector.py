from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.connectors.base import ConnectorFailure
from app.connectors.confluence import ConfluenceConnector
from app.schemas.connection import ConfluenceCredentials
from app.schemas.ingestion import ConfluenceConfig


CREDS = {
    "kind": "confluence",
    "site_url": "https://docs.atlassian.net",
    "email": "reader@example.com",
    "api_token": "fixture-token",
}


def config(**updates):
    values = {
        "kind": "confluence",
        "connection_id": "11111111-1111-4111-8111-111111111111",
        "selection": {"mode": "site"},
        "max_pages": 10,
        "max_api_pages": 10,
        "max_response_bytes": 10_000,
        "max_text_chars": 10_000,
        "request_timeout_seconds": 5,
    }
    values.update(updates)
    return ConfluenceConfig.model_validate(values)


class Response:
    def __init__(self, payload, status=200, headers=None):
        import json

        self._payload = payload
        self.status_code = status
        self.content = json.dumps(payload).encode()
        self.headers = headers or {}

    def json(self):
        return self._payload


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, params=None):
        self.calls.append((method, path, params))
        return self.responses.pop(0)

    def close(self):
        pass


def public_dns(*args, **kwargs):
    return [(2, 1, 6, "", ("104.192.142.10", 443))]


PAGE = {
    "id": "123",
    "status": "current",
    "title": "Handbook",
    "spaceId": "44",
    "version": {"number": 7, "createdAt": "2026-09-12T10:00:00Z"},
    "_links": {"webui": "/spaces/ENG/pages/123"},
}


def test_credentials_reject_non_atlassian_and_non_root_urls():
    for url in (
        "http://docs.atlassian.net",
        "https://example.com",
        "https://docs.atlassian.net/wiki",
    ):
        with pytest.raises(ValidationError):
            ConfluenceCredentials.model_validate({**CREDS, "site_url": url})


def test_discovery_paginates_filters_and_keeps_stable_revision():
    other = {**PAGE, "id": "124", "title": "Private draft"}
    client = Client(
        [
            Response(
                {
                    "results": [PAGE],
                    "_links": {"next": "/wiki/api/v2/pages?cursor=next"},
                }
            ),
            Response({"results": [other], "_links": {}}),
        ]
    )
    connector = ConfluenceConnector(
        CREDS, client_factory=lambda *_: client, resolver=public_dns
    )
    outcomes = connector.discover_all(
        config(title_prefixes=["Hand"], exclude_title_prefixes=["Private"])
    )
    assert [(value.external_id, value.status) for value in outcomes] == [
        ("123", "included"),
        ("124", "excluded"),
    ]
    assert outcomes[0].provider_revision == "version:7:2026-09-12T10:00:00Z"
    assert client.calls[1][2]["cursor"] == "next"


def test_fetch_extracts_storage_sections_and_rechecks_version():
    body = {
        **PAGE,
        "body": {
            "storage": {
                "value": "<h1>Guide</h1><p>Hello <b>team</b>.</p><script>bad()</script><li>Step one</li>"
            }
        },
    }
    discover_client = Client(
        [Response({"results": [PAGE], "_links": {}}), Response(body)]
    )
    connector = ConfluenceConnector(
        CREDS,
        client_factory=lambda *_: discover_client,
        resolver=public_dns,
        clock=lambda: datetime(2026, 9, 13, tzinfo=UTC),
    )
    item = connector.discover(config()).items[0]
    artifact = connector.fetch(config(), item)
    assert artifact.content == b"Guide\nHello team.\nStep one"
    assert artifact.segments[1].section_path == ("Guide",)
    assert b"bad" not in artifact.content


def test_redirect_is_rejected_without_following_it():
    client = Client(
        [Response({}, status=302, headers={"location": "https://evil.example/"})]
    )
    connector = ConfluenceConnector(
        CREDS, client_factory=lambda *_: client, resolver=public_dns
    )
    with pytest.raises(
        ConnectorFailure, match="credentials were not forwarded"
    ) as raised:
        connector.discover_all(config())
    assert raised.value.issue.code == "unsafe_redirect"


def test_fetch_all_skips_body_for_unchanged_provider_revision():
    client = Client([Response({"results": [PAGE], "_links": {}})])
    connector = ConfluenceConnector(
        CREDS, client_factory=lambda *_: client, resolver=public_dns
    )

    class Prior:
        provider_revision = "version:7:2026-09-12T10:00:00Z"
        processing_config_hash = "processing"
        content_hash = "a" * 64

    _, artifacts = connector.fetch_all(
        config(), {"confluence://docs.atlassian.net/page/123": Prior()}, "processing"
    )
    assert artifacts[0].unchanged is True
    assert len(client.calls) == 1


def test_operation_request_budget_includes_discovery_and_every_body_fetch():
    second = {**PAGE, "id": "124"}
    body = {**PAGE, "body": {"storage": {"value": "<p>body</p>"}}}
    client = Client(
        [Response({"results": [PAGE, second], "_links": {}}), Response(body)]
    )
    connector = ConfluenceConnector(
        CREDS, client_factory=lambda *_: client, resolver=public_dns
    )
    with pytest.raises(ConnectorFailure) as raised:
        connector.fetch_all(config(max_api_pages=2), {}, "processing")
    assert raised.value.issue.code == "request_limit_exceeded"
    assert len(client.calls) == 2


def test_page_limit_stops_during_provider_page_iteration():
    second = {**PAGE, "id": "124"}
    client = Client([Response({"results": [PAGE, second], "_links": {}})])
    connector = ConfluenceConnector(
        CREDS, client_factory=lambda *_: client, resolver=public_dns
    )
    with pytest.raises(ConnectorFailure) as raised:
        connector.discover_all(config(max_pages=1))
    assert raised.value.issue.code == "page_limit_exceeded"
    assert len(client.calls) == 1


def test_cancellation_stops_before_scheduling_the_next_provider_request():
    client = Client([Response({"results": [PAGE], "_links": {}})])
    checks = iter([False, True])
    connector = ConfluenceConnector(
        CREDS,
        client_factory=lambda *_: client,
        resolver=public_dns,
        cancellation_check=lambda: next(checks),
    )
    with pytest.raises(ConnectorFailure) as raised:
        connector.fetch_all(config(), {}, "processing")
    assert raised.value.issue.code == "cancelled"
    assert len(client.calls) == 1
