"""Bounded Notion discovery and deterministic block extraction."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import UUID

import httpx

from app.connectors.base import (
    ConnectionCheck,
    ConnectorFailure,
    ConnectorIssue,
    DiscoveredItem,
    DiscoveryPage,
)
from app.connectors.connections import ConnectionCheck as ConnectionResult
from app.schemas.ingestion import NotionConfig


API_ROOT = "https://api.notion.com/v1"
API_VERSION = "2026-03-11"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class NotionPreviewOutcome:
    external_id: str | None
    display_name: str
    canonical_location: str | None
    provider_revision: str | None
    media_type: str | None
    status: str
    reason: str
    size_bytes: int | None = None
    depth: int | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class NotionSegment:
    text: str
    block_id: str
    block_type: str
    depth: int
    section_path: tuple[str, ...]


@dataclass(frozen=True)
class NotionArtifact:
    item: DiscoveredItem
    content: bytes | None
    content_hash: str | None
    segments: tuple[NotionSegment, ...]
    fetched_at: datetime
    unchanged: bool = False


def _client(credentials: dict, timeout: float):
    return httpx.Client(
        base_url=API_ROOT,
        timeout=httpx.Timeout(timeout),
        headers={
            "Authorization": f"Bearer {credentials['integration_token']}",
            "Notion-Version": API_VERSION,
            "Content-Type": "application/json",
        },
    )


def _issue(status: int | None, code: str | None = None):
    if status == 401 or code == "unauthorized":
        return ConnectorIssue(
            code="authentication_failed",
            message="Notion rejected the configured integration token.",
            retryable=False,
        )
    if status == 403 or code == "restricted_resource":
        return ConnectorIssue(
            code="permission_denied",
            message="Notion denied access to the requested content.",
            retryable=False,
        )
    if status == 404 or code == "object_not_found":
        return ConnectorIssue(
            code="not_found",
            message="The Notion page or data source is unavailable or not shared.",
            retryable=False,
        )
    if status == 429 or code == "rate_limited":
        return ConnectorIssue(
            code="provider_throttled",
            message="Notion temporarily limited this request.",
            retryable=True,
        )
    if status in {500, 502, 503, 504}:
        return ConnectorIssue(
            code="provider_unavailable",
            message="Notion is temporarily unavailable.",
            retryable=True,
        )
    return ConnectorIssue(
        code="provider_error",
        message="Notion could not complete the requested operation.",
        retryable=False,
    )


def _plain_text(values: Any):
    if not isinstance(values, list):
        return ""
    return "".join(
        str(value.get("plain_text", "")) for value in values if isinstance(value, dict)
    ).strip()


def _title(page: dict):
    for value in page.get("properties", {}).values():
        if isinstance(value, dict) and value.get("type") == "title":
            title = _plain_text(value.get("title"))
            if title:
                return title
    return "Untitled Notion page"


def _page_item(page: dict):
    page_id = str(UUID(str(page["id"])))
    edited = str(page.get("last_edited_time") or "unknown")
    parent = page.get("parent") if isinstance(page.get("parent"), dict) else {}
    parent_id = next(
        (str(value) for key, value in parent.items() if key.endswith("_id")), None
    )
    return DiscoveredItem(
        external_id=page_id,
        display_name=_title(page),
        canonical_location=f"notion://page/{page_id}",
        media_type="text/plain",
        provider_revision=f"last-edited:{edited}",
        modified_at=(
            datetime.fromisoformat(edited.replace("Z", "+00:00"))
            if edited != "unknown"
            else None
        ),
        parent_external_id=parent_id,
        metadata={
            "page_id": page_id,
            "url": str(page.get("url") or ""),
            "parent_type": str(parent.get("type") or "unknown"),
            "parent_id": parent_id,
            "last_edited_time": edited,
        },
    )


class NotionApi:
    def __init__(
        self,
        client,
        max_requests: int,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.max_requests = max_requests
        self.requests = 0
        self.sleeper = sleeper

    def request(self, method: str, path: str, **kwargs):
        for attempt in range(2):
            self.requests += 1
            if self.requests > self.max_requests:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="request_limit_exceeded",
                        message="Notion exceeded the configured API request-page limit.",
                        retryable=False,
                    )
                )
            try:
                response = self.client.request(method, path, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    self.sleeper(0.1)
                    continue
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="endpoint_unreachable",
                        message="Notion could not be reached within the configured timeout.",
                        retryable=True,
                    )
                ) from None
            if response.status_code < 400:
                try:
                    return response.json()
                except ValueError:
                    raise ConnectorFailure(_issue(None)) from None
            try:
                error = response.json()
                code = error.get("code") if isinstance(error, dict) else None
            except ValueError:
                code = None
            issue = _issue(response.status_code, code)
            if response.status_code in RETRYABLE_STATUS and attempt == 0:
                retry_after = response.headers.get("retry-after")
                try:
                    delay = min(2.0, max(0.0, float(retry_after or 0.1)))
                except ValueError:
                    delay = 0.1
                self.sleeper(delay)
                continue
            raise ConnectorFailure(issue)
        raise AssertionError("bounded request loop exhausted")


class NotionConnectionTester:
    def __init__(self, client_factory: Callable = _client):
        self.client_factory = client_factory

    def check(self, credentials: dict):
        client = self.client_factory(credentials, 10)
        try:
            NotionApi(client, 2).request("GET", "/users/me")
        except ConnectorFailure as exc:
            code = (
                exc.issue.code
                if exc.issue.code
                in {
                    "authentication_failed",
                    "permission_denied",
                    "endpoint_unreachable",
                }
                else "endpoint_unreachable"
            )
            return ConnectionResult("failed", code)
        finally:
            close = getattr(client, "close", None)
            if close:
                close()
        return ConnectionResult("succeeded", "ok")


class NotionConnector:
    kind = "notion"
    config_version = "1"

    def __init__(
        self,
        credentials: dict,
        *,
        client_factory: Callable = _client,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if credentials.get("kind") != "notion":
            raise ConnectorFailure(
                ConnectorIssue(
                    code="connection_kind_mismatch",
                    message="The selected source connection is not a Notion connection.",
                    retryable=False,
                )
            )
        self.credentials = credentials
        self.client_factory = client_factory
        self.clock = clock
        self.sleeper = sleeper
        self._pages: dict[str, dict] = {}

    def validate(self, config: object, connection: object | None = None) -> None:
        NotionConfig.model_validate(config)

    def test_connection(self, connection: object | None = None) -> ConnectionCheck:
        result = NotionConnectionTester(self.client_factory).check(self.credentials)
        if result.outcome == "succeeded":
            return ConnectionCheck(status="available", message="Notion is reachable.")
        return ConnectionCheck(status="unavailable", message="Notion is unavailable.")

    def _api(self, config: NotionConfig):
        client = self.client_factory(self.credentials, config.request_timeout_seconds)
        return client, NotionApi(client, config.max_api_pages, sleeper=self.sleeper)

    @staticmethod
    def _paginate(api: NotionApi, method: str, path: str, body: dict | None = None):
        cursor = None
        while True:
            payload = {**(body or {}), "page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            if method == "POST":
                response = api.request(method, path, json=payload)
            else:
                response = api.request(method, path, params=payload)
            yield from response.get("results", ())
            if not response.get("has_more"):
                return
            cursor = response.get("next_cursor")
            if not cursor:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="invalid_provider_page",
                        message="Notion returned an invalid pagination cursor.",
                        retryable=True,
                    )
                )

    def _discover_pages(self, config: NotionConfig, api: NotionApi):
        selection = config.selection
        if selection.mode == "workspace":
            yield from self._paginate(
                api,
                "POST",
                "/search",
                {"filter": {"property": "object", "value": "page"}},
            )
        elif selection.mode == "pages":
            for page_id in selection.page_ids:
                yield api.request("GET", f"/pages/{page_id}")
        else:
            for data_source_id in selection.data_source_ids:
                yield from self._paginate(
                    api,
                    "POST",
                    f"/data_sources/{data_source_id}/query",
                )

    def discover_all(self, config: object):
        parsed = NotionConfig.model_validate(config)
        client, api = self._api(parsed)
        try:
            pages = list(self._discover_pages(parsed, api))
        finally:
            close = getattr(client, "close", None)
            if close:
                close()
        if len(pages) > parsed.max_pages:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="page_limit_exceeded",
                    message="Notion discovery exceeded the configured page limit.",
                    retryable=False,
                )
            )
        outcomes = []
        self._pages = {}
        for page in sorted(pages, key=lambda value: str(value.get("id", ""))):
            try:
                item = _page_item(page)
            except (KeyError, ValueError, TypeError):
                outcomes.append(
                    NotionPreviewOutcome(
                        external_id=None,
                        display_name="Invalid Notion page",
                        canonical_location=None,
                        provider_revision=None,
                        media_type=None,
                        status="failed",
                        reason="Notion returned an invalid page identity.",
                        error_code="invalid_page",
                    )
                )
                continue
            if item.external_id in self._pages:
                outcomes.append(
                    NotionPreviewOutcome(
                        external_id=item.external_id,
                        display_name=item.display_name,
                        canonical_location=item.canonical_location,
                        provider_revision=item.provider_revision,
                        media_type=item.media_type,
                        status="duplicate",
                        reason="Notion page was discovered more than once.",
                    )
                )
                continue
            self._pages[item.external_id] = page
            trashed = bool(page.get("in_trash") or page.get("archived"))
            outcomes.append(
                NotionPreviewOutcome(
                    external_id=item.external_id,
                    display_name=item.display_name,
                    canonical_location=item.canonical_location,
                    provider_revision=item.provider_revision,
                    media_type=item.media_type,
                    status="excluded" if trashed else "included",
                    reason=(
                        "Notion page is in trash."
                        if trashed
                        else "Notion page is shared and ready to ingest."
                    ),
                )
            )
        return outcomes

    def discover(self, config: object, cursor: str | None = None) -> DiscoveryPage:
        if cursor is not None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="invalid_cursor",
                    message="Notion connector cursors are managed inside bounded discovery.",
                    retryable=False,
                )
            )
        outcomes = self.discover_all(config)
        return DiscoveryPage(
            items=tuple(
                _page_item(self._pages[outcome.external_id])
                for outcome in outcomes
                if outcome.status == "included" and outcome.external_id
            )
        )

    @staticmethod
    def _segment(block: dict, depth: int, sections: list[str]):
        kind = str(block.get("type") or "unsupported")
        value = block.get(kind) if isinstance(block.get(kind), dict) else {}
        if kind == "equation":
            text = str(value.get("expression") or "").strip()
        elif kind == "child_page":
            text = str(value.get("title") or "").strip()
        elif kind == "child_database":
            text = str(value.get("title") or "").strip()
        elif kind == "table_row":
            text = " | ".join(_plain_text(cell) for cell in value.get("cells", ()))
        else:
            text = _plain_text(value.get("rich_text"))
        if not text:
            return None, sections
        if kind in {"heading_1", "heading_2", "heading_3", "heading_4"}:
            level = int(kind.rsplit("_", 1)[1])
            sections = sections[: level - 1] + [text]
        prefix = {
            "bulleted_list_item": "• ",
            "numbered_list_item": "1. ",
            "to_do": "[x] " if value.get("checked") else "[ ] ",
            "quote": "> ",
        }.get(kind, "")
        return (
            NotionSegment(
                text=f"{prefix}{text}",
                block_id=str(block.get("id") or "unknown"),
                block_type=kind,
                depth=depth,
                section_path=tuple(sections),
            ),
            sections,
        )

    def fetch(self, config: object, item: DiscoveredItem):
        parsed = NotionConfig.model_validate(config)
        client, api = self._api(parsed)
        segments: list[NotionSegment] = []
        block_count = 0
        text_chars = 0

        def walk(parent_id: str, depth: int, sections: list[str]):
            nonlocal block_count, text_chars
            if depth > parsed.max_block_depth:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="block_depth_exceeded",
                        message="Notion content exceeded the configured block depth.",
                        retryable=False,
                    )
                )
            local_sections = list(sections)
            for block in self._paginate(api, "GET", f"/blocks/{parent_id}/children"):
                block_count += 1
                if block_count > parsed.max_blocks_per_page:
                    raise ConnectorFailure(
                        ConnectorIssue(
                            code="block_limit_exceeded",
                            message="Notion content exceeded the configured block limit.",
                            retryable=False,
                        )
                    )
                segment, local_sections = self._segment(block, depth, local_sections)
                if segment:
                    text_chars += len(segment.text) + 1
                    if text_chars > parsed.max_text_chars:
                        raise ConnectorFailure(
                            ConnectorIssue(
                                code="text_limit_exceeded",
                                message="Notion content exceeded the configured text limit.",
                                retryable=False,
                            )
                        )
                    segments.append(segment)
                if block.get("has_children"):
                    walk(str(block["id"]), depth + 1, local_sections)

        try:
            walk(item.external_id, 0, [])
            current = api.request("GET", f"/pages/{item.external_id}")
        finally:
            close = getattr(client, "close", None)
            if close:
                close()
        current_item = _page_item(current)
        if current_item.provider_revision != item.provider_revision:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="page_changed",
                    message="The Notion page changed after discovery. Retry the run.",
                    retryable=True,
                )
            )
        content = "\n".join(segment.text for segment in segments).encode("utf-8")
        if not content:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="empty_page",
                    message="The Notion page contains no supported text blocks.",
                    retryable=False,
                )
            )
        return NotionArtifact(
            item=item,
            content=content,
            content_hash=hashlib.sha256(content).hexdigest(),
            segments=tuple(segments),
            fetched_at=self.clock(),
        )

    def fetch_all(
        self,
        config: object,
        priors: dict[str, object],
        processing_config_hash: str,
    ):
        parsed = NotionConfig.model_validate(config)
        outcomes = self.discover_all(parsed)
        artifacts = []
        for outcome in outcomes:
            if outcome.status != "included" or not outcome.external_id:
                continue
            page = self._pages[outcome.external_id]
            item = _page_item(page)
            prior = priors.get(item.canonical_location)
            if (
                prior is not None
                and prior.provider_revision == item.provider_revision
                and prior.processing_config_hash == processing_config_hash
            ):
                artifacts.append(
                    NotionArtifact(
                        item=item,
                        content=None,
                        content_hash=prior.content_hash,
                        segments=(),
                        fetched_at=self.clock(),
                        unchanged=True,
                    )
                )
            else:
                artifacts.append(self.fetch(parsed, item))
        return outcomes, artifacts
