from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.connectors.base import ConnectorFailure
from app.connectors.notion import NotionConnectionTester, NotionConnector
from app.schemas.ingestion import NotionConfig


NOW = "2026-09-13T12:00:00.000Z"
CREDS = {"kind": "notion", "integration_token": "fixture-notion-token"}


def page(page_id, title, edited=NOW, *, trashed=False, parent=None):
    return {
        "object": "page",
        "id": page_id,
        "last_edited_time": edited,
        "in_trash": trashed,
        "url": f"https://www.notion.so/{page_id}",
        "parent": parent or {"type": "workspace", "workspace": True},
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": title}],
            }
        },
    }


PAGE_A = "11111111-1111-4111-8111-111111111111"
PAGE_B = "22222222-2222-4222-8222-222222222222"
DATA_SOURCE = "33333333-3333-4333-8333-333333333333"


class Response:
    def __init__(self, status, value, headers=None):
        self.status_code = status
        self.value = value
        self.headers = headers or {}

    def json(self):
        return self.value


class NotionDouble:
    def __init__(self):
        self.calls = []
        self.pages = {
            PAGE_A: page(PAGE_A, "Orchard handbook"),
            PAGE_B: page(PAGE_B, "Archived notes", trashed=True),
        }
        self.blocks = {
            PAGE_A: [
                {
                    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "type": "heading_1",
                    "heading_1": {"rich_text": [{"plain_text": "Harvest"}]},
                    "has_children": False,
                },
                {
                    "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"plain_text": "The orchard grows apples."}]
                    },
                    "has_children": True,
                },
            ],
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": [
                {
                    "id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"plain_text": "Inspect ladders."}]
                    },
                    "has_children": False,
                }
            ],
        }
        self.closed = False

    def close(self):
        self.closed = True

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/users/me":
            return Response(200, {"object": "user", "id": "bot"})
        if path == "/search":
            return Response(
                200,
                {
                    "results": list(self.pages.values()),
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        if path == f"/data_sources/{DATA_SOURCE}/query":
            return Response(
                200,
                {"results": [self.pages[PAGE_A]], "has_more": False},
            )
        if path.startswith("/pages/"):
            return Response(200, self.pages[path.rsplit("/", 1)[1]])
        if path.startswith("/blocks/"):
            block_id = path.split("/")[2]
            return Response(
                200,
                {"results": self.blocks.get(block_id, []), "has_more": False},
            )
        raise AssertionError(path)


def config(selection=None, **changes):
    values = {
        "kind": "notion",
        "connection_id": uuid4(),
        "selection": selection or {"mode": "workspace"},
        "max_pages": 10,
        "max_api_pages": 20,
        "max_blocks_per_page": 20,
        "max_block_depth": 4,
        "max_text_chars": 10000,
        "request_timeout_seconds": 5,
    }
    values.update(changes)
    return NotionConfig.model_validate(values)


def factory(double, captured=None):
    def create(credentials, timeout):
        if captured is not None:
            captured.append((credentials, timeout))
        return double

    return create


def test_workspace_discovery_exposes_stable_revision_and_trash_state():
    double, captured = NotionDouble(), []
    outcomes = NotionConnector(
        CREDS, client_factory=factory(double, captured)
    ).discover_all(config())
    assert [(item.display_name, item.status) for item in outcomes] == [
        ("Orchard handbook", "included"),
        ("Archived notes", "excluded"),
    ]
    assert outcomes[0].canonical_location == f"notion://page/{PAGE_A}"
    assert outcomes[0].provider_revision == f"last-edited:{NOW}"
    assert captured == [(CREDS, 5.0)]
    search = next(call for call in double.calls if call[1] == "/search")
    assert search[2]["json"]["filter"] == {
        "property": "object",
        "value": "page",
    }


def test_nested_block_fetch_and_unchanged_shortcut():
    double = NotionDouble()
    connector = NotionConnector(
        CREDS,
        client_factory=factory(double),
        clock=lambda: datetime(2026, 9, 13, tzinfo=UTC),
    )
    outcomes, artifacts = connector.fetch_all(config(), {}, "a" * 64)
    assert len(outcomes) == 2 and len(artifacts) == 1
    artifact = artifacts[0]
    assert (
        artifact.content
        == b"Harvest\nThe orchard grows apples.\n\xe2\x80\xa2 Inspect ladders."
    )
    assert [segment.section_path for segment in artifact.segments] == [
        ("Harvest",),
        ("Harvest",),
        ("Harvest",),
    ]
    prior = SimpleNamespace(
        provider_revision=artifact.item.provider_revision,
        processing_config_hash="a" * 64,
        content_hash=artifact.content_hash,
    )
    double.calls.clear()
    _, refreshed = connector.fetch_all(
        config(), {artifact.item.canonical_location: prior}, "a" * 64
    )
    assert refreshed[0].unchanged and refreshed[0].content is None
    assert not any(call[1].startswith("/blocks/") for call in double.calls)


def test_data_source_selection_connection_check_and_safe_errors():
    double = NotionDouble()
    outcomes = NotionConnector(CREDS, client_factory=factory(double)).discover_all(
        config({"mode": "data_sources", "data_source_ids": [DATA_SOURCE]})
    )
    assert [item.external_id for item in outcomes] == [PAGE_A]
    check = NotionConnectionTester(factory(double)).check(CREDS)
    assert (check.outcome, check.code) == ("succeeded", "ok")

    class Denied(NotionDouble):
        def request(self, method, path, **kwargs):
            return Response(
                403,
                {
                    "code": "restricted_resource",
                    "message": "echo fixture-notion-token",
                },
            )

    with pytest.raises(ConnectorFailure) as failure:
        NotionConnector(
            CREDS, client_factory=factory(Denied()), sleeper=lambda _: None
        ).discover_all(config())
    assert failure.value.issue.code == "permission_denied"
    assert "fixture-notion-token" not in failure.value.issue.message


def test_cursor_pagination_and_request_limit_are_bounded():
    class Paginated(NotionDouble):
        def request(self, method, path, **kwargs):
            self.calls.append((method, path, kwargs))
            if path != "/search":
                return super().request(method, path, **kwargs)
            cursor = kwargs["json"].get("start_cursor")
            if cursor is None:
                return Response(
                    200,
                    {
                        "results": [self.pages[PAGE_A]],
                        "has_more": True,
                        "next_cursor": "page-two",
                    },
                )
            assert cursor == "page-two"
            return Response(
                200,
                {"results": [self.pages[PAGE_B]], "has_more": False},
            )

    double = Paginated()
    outcomes = NotionConnector(CREDS, client_factory=factory(double)).discover_all(
        config()
    )
    assert [item.external_id for item in outcomes] == [PAGE_A, PAGE_B]
    assert len([call for call in double.calls if call[1] == "/search"]) == 2
    with pytest.raises(ConnectorFailure) as failure:
        NotionConnector(CREDS, client_factory=factory(Paginated())).discover_all(
            config(max_api_pages=1)
        )
    assert failure.value.issue.code == "request_limit_exceeded"


def test_nested_content_depth_limit_fails_closed():
    connector = NotionConnector(CREDS, client_factory=factory(NotionDouble()))
    item = connector.discover(config({"mode": "pages", "page_ids": [PAGE_A]})).items[0]
    with pytest.raises(ConnectorFailure) as failure:
        connector.fetch(config(max_block_depth=0), item)
    assert failure.value.issue.code == "block_depth_exceeded"


def test_schema_rejects_duplicate_or_unbounded_selections():
    with pytest.raises(ValidationError):
        config({"mode": "pages", "page_ids": [PAGE_A, PAGE_A]})
    with pytest.raises(ValidationError):
        config(max_block_depth=17)
