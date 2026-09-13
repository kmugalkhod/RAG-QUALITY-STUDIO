"""Bounded Confluence Cloud REST v2 discovery and storage-body extraction."""

from __future__ import annotations

import hashlib
import json
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import parse_qs, urlsplit

import httpx

from app.connectors.base import (
    ConnectionCheck,
    ConnectorFailure,
    ConnectorIssue,
    DiscoveredItem,
    DiscoveryPage,
)
from app.connectors.connections import ConnectionCheck as ConnectionResult
from app.connectors.safe_http import resolve_public
from app.schemas.ingestion import ConfluenceConfig


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ConfluencePreviewOutcome:
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
class ConfluenceSegment:
    text: str
    element: str
    ordinal: int
    section_path: tuple[str, ...]


@dataclass(frozen=True)
class ConfluenceArtifact:
    item: DiscoveredItem
    content: bytes | None
    content_hash: str | None
    segments: tuple[ConfluenceSegment, ...]
    fetched_at: datetime
    unchanged: bool = False


def _site(credentials: dict) -> tuple[str, str]:
    value = str(credentials.get("site_url", "")).rstrip("/")
    parts = urlsplit(value)
    host = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or not host.endswith(".atlassian.net")
        or host == "atlassian.net"
        or parts.port not in (None, 443)
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or parts.username
        or parts.password
    ):
        raise ConnectorFailure(
            ConnectorIssue(
                code="unsafe_site_url",
                message="Confluence requires a root HTTPS *.atlassian.net Cloud URL.",
                retryable=False,
            )
        )
    return f"https://{host}", host


def _client(credentials: dict, timeout: float):
    site, _ = _site(credentials)
    return httpx.Client(
        base_url=f"{site}/wiki/api/v2",
        timeout=httpx.Timeout(timeout),
        auth=(credentials["email"], credentials["api_token"]),
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "RAG-Quality-Studio/1"},
    )


def _issue(status: int | None):
    if status == 401:
        return ConnectorIssue(
            code="authentication_failed",
            message="Confluence rejected the configured account or API token.",
            retryable=False,
        )
    if status == 403:
        return ConnectorIssue(
            code="permission_denied",
            message="Confluence denied access to the requested content.",
            retryable=False,
        )
    if status == 404:
        return ConnectorIssue(
            code="not_found",
            message="The Confluence page or space is unavailable to this account.",
            retryable=False,
        )
    if status == 429:
        return ConnectorIssue(
            code="provider_throttled",
            message="Confluence temporarily limited this request.",
            retryable=True,
        )
    if status in RETRYABLE_STATUS:
        return ConnectorIssue(
            code="provider_unavailable",
            message="Confluence is temporarily unavailable.",
            retryable=True,
        )
    if status is not None and 300 <= status < 400:
        return ConnectorIssue(
            code="unsafe_redirect",
            message="Confluence returned a redirect; credentials were not forwarded.",
            retryable=False,
        )
    return ConnectorIssue(
        code="provider_error",
        message="Confluence could not complete the requested operation.",
        retryable=False,
    )


class ConfluenceApi:
    def __init__(
        self,
        client,
        host: str,
        max_requests: int,
        max_bytes: int,
        *,
        resolver=socket.getaddrinfo,
        sleeper=time.sleep,
        cancellation_check: Callable[[], bool] = lambda: False,
    ):
        self.client = client
        self.host = host
        self.max_requests = max_requests
        self.max_bytes = max_bytes
        self.resolver = resolver
        self.sleeper = sleeper
        self.cancellation_check = cancellation_check
        self.requests = 0

    def request(self, path: str, *, params: dict | None = None):
        for attempt in range(2):
            if self.cancellation_check():
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="cancelled",
                        message="Confluence ingestion was cancelled.",
                        retryable=False,
                    )
                )
            self.requests += 1
            if self.requests > self.max_requests:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="request_limit_exceeded",
                        message="Confluence exceeded the configured API request-page limit.",
                        retryable=False,
                    )
                )
            resolve_public(self.host, 443, self.resolver)
            try:
                if hasattr(self.client, "stream"):
                    with self.client.stream("GET", path, params=params) as streamed:
                        response_status = streamed.status_code
                        response_headers = streamed.headers
                        chunks = []
                        transferred = 0
                        for chunk in streamed.iter_bytes():
                            transferred += len(chunk)
                            if transferred > self.max_bytes:
                                raise ConnectorFailure(
                                    ConnectorIssue(
                                        code="response_too_large",
                                        message="Confluence returned more data than the configured response limit.",
                                        retryable=False,
                                    )
                                )
                            chunks.append(chunk)
                        response_content = b"".join(chunks)
                else:
                    response = self.client.request("GET", path, params=params)
                    response_status = response.status_code
                    response_headers = response.headers
                    response_content = response.content
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    self.sleeper(0.1)
                    continue
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="endpoint_unreachable",
                        message="Confluence could not be reached within the configured timeout.",
                        retryable=True,
                    )
                ) from None
            length = response_headers.get("content-length")
            if (length and length.isdigit() and int(length) > self.max_bytes) or len(
                response_content
            ) > self.max_bytes:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="response_too_large",
                        message="Confluence returned more data than the configured response limit.",
                        retryable=False,
                    )
                )
            if response_status < 300:
                try:
                    payload = json.loads(response_content)
                except (ValueError, UnicodeDecodeError):
                    raise ConnectorFailure(_issue(None)) from None
                if not isinstance(payload, dict):
                    raise ConnectorFailure(_issue(None))
                return payload
            issue = _issue(response_status)
            if response_status in RETRYABLE_STATUS and attempt == 0:
                retry_after = response_headers.get("retry-after", "0.1")
                try:
                    delay = min(2.0, max(0.0, float(retry_after)))
                except ValueError:
                    delay = 0.1
                self.sleeper(delay)
                continue
            raise ConnectorFailure(issue)
        raise AssertionError("bounded request loop exhausted")


def _page_item(page: dict, site: str):
    page_id = str(page["id"])
    if not page_id.isdigit():
        raise ValueError("invalid page ID")
    version = page.get("version") if isinstance(page.get("version"), dict) else {}
    number = int(version["number"])
    changed = str(version.get("createdAt") or "unknown")
    webui = str((page.get("_links") or {}).get("webui") or "")
    modified = (
        None
        if changed == "unknown"
        else datetime.fromisoformat(changed.replace("Z", "+00:00"))
    )
    return DiscoveredItem(
        external_id=page_id,
        display_name=str(page.get("title") or "Untitled Confluence page")[:500],
        canonical_location=f"confluence://{urlsplit(site).hostname}/page/{page_id}",
        media_type="text/plain",
        provider_revision=f"version:{number}:{changed}",
        modified_at=modified,
        parent_external_id=str(page.get("parentId")) if page.get("parentId") else None,
        metadata={
            "page_id": page_id,
            "space_id": str(page.get("spaceId") or ""),
            "parent_id": str(page.get("parentId") or ""),
            "parent_type": str(page.get("parentType") or ""),
            "status": str(page.get("status") or ""),
            "version": number,
            "version_created_at": changed,
            "web_url": f"{site}{webui}" if webui.startswith("/") else "",
        },
    )


class _StorageParser(HTMLParser):
    blocks = {
        "p",
        "li",
        "blockquote",
        "pre",
        "td",
        "th",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current: list[str] = []
        self.tag = "p"
        self.sections: list[str] = []
        self.segments: list[ConfluenceSegment] = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        if not self.ignored and tag in self.blocks:
            self._flush()
            self.tag = tag

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1
        elif not self.ignored and tag in self.blocks:
            self._flush()

    def handle_data(self, data):
        if not self.ignored:
            self.current.append(data)

    def _flush(self):
        text = " ".join("".join(self.current).split())
        self.current = []
        if not text:
            return
        if self.tag.startswith("h") and self.tag[1:].isdigit():
            level = int(self.tag[1:])
            self.sections = self.sections[: level - 1] + [text]
        self.segments.append(
            ConfluenceSegment(
                text=text,
                element=self.tag,
                ordinal=len(self.segments),
                section_path=tuple(self.sections),
            )
        )

    def finish(self):
        self._flush()
        return tuple(self.segments)


class ConfluenceConnectionTester:
    def __init__(
        self, client_factory: Callable = _client, *, resolver=socket.getaddrinfo
    ):
        self.client_factory = client_factory
        self.resolver = resolver

    def check(self, credentials: dict):
        try:
            site, host = _site(credentials)
            client = self.client_factory(credentials, 10)
            ConfluenceApi(client, host, 2, 256_000, resolver=self.resolver).request(
                "/spaces", params={"limit": 1}
            )
        except ConnectorFailure as exc:
            return ConnectionResult("failed", exc.issue.code)
        finally:
            if "client" in locals() and getattr(client, "close", None):
                client.close()
        return ConnectionResult("succeeded", "ok")


class ConfluenceConnector:
    kind = "confluence"
    config_version = "1"

    def __init__(
        self,
        credentials: dict,
        *,
        client_factory: Callable = _client,
        resolver=socket.getaddrinfo,
        clock=lambda: datetime.now(UTC),
        sleeper=time.sleep,
        cancellation_check: Callable[[], bool] = lambda: False,
    ):
        if credentials.get("kind") != "confluence":
            raise ConnectorFailure(
                ConnectorIssue(
                    code="connection_kind_mismatch",
                    message="The selected source connection is not a Confluence connection.",
                    retryable=False,
                )
            )
        self.credentials = credentials
        self.site, self.host = _site(credentials)
        self.client_factory = client_factory
        self.resolver = resolver
        self.clock = clock
        self.sleeper = sleeper
        self.cancellation_check = cancellation_check
        self._pages: dict[str, dict] = {}

    def validate(self, config, connection=None):
        ConfluenceConfig.model_validate(config)

    def test_connection(self, connection=None):
        result = ConfluenceConnectionTester(
            self.client_factory, resolver=self.resolver
        ).check(self.credentials)
        return ConnectionCheck(
            status="available" if result.outcome == "succeeded" else "unavailable",
            message="Confluence is reachable."
            if result.outcome == "succeeded"
            else "Confluence is unavailable.",
        )

    def _api(self, config):
        client = self.client_factory(self.credentials, config.request_timeout_seconds)
        return client, ConfluenceApi(
            client,
            self.host,
            config.max_api_pages,
            config.max_response_bytes,
            resolver=self.resolver,
            sleeper=self.sleeper,
            cancellation_check=self.cancellation_check,
        )

    @staticmethod
    def _paginate(api, path, params=None):
        cursor = None
        while True:
            query = {**(params or {}), "limit": 250}
            if cursor:
                query["cursor"] = cursor
            response = api.request(path, params=query)
            results = response.get("results")
            if not isinstance(results, list):
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="invalid_provider_page",
                        message="Confluence returned an invalid result page.",
                        retryable=True,
                    )
                )
            yield from results
            next_url = (response.get("_links") or {}).get("next")
            if not next_url:
                return
            parts = urlsplit(str(next_url))
            if parts.hostname and parts.hostname.lower() != api.host:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="unsafe_pagination_url",
                        message="Confluence returned pagination for another origin.",
                        retryable=False,
                    )
                )
            cursors = parse_qs(parts.query).get("cursor")
            if not cursors or not cursors[0]:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="invalid_provider_page",
                        message="Confluence returned an invalid pagination cursor.",
                        retryable=True,
                    )
                )
            cursor = cursors[0]

    def _selected_pages(self, config, api):
        def bounded(values):
            result = []
            for value in values:
                if len(result) >= config.max_pages:
                    raise ConnectorFailure(
                        ConnectorIssue(
                            code="page_limit_exceeded",
                            message="Confluence discovery exceeded the configured page limit.",
                            retryable=False,
                        )
                    )
                result.append(value)
            return result

        selection = config.selection
        if selection.mode == "pages":
            pages = [
                api.request(f"/pages/{page_id}", params={"include-version": "true"})
                for page_id in selection.page_ids
            ]
        elif selection.mode == "spaces":
            pages = bounded(
                page
                for space_id in selection.space_ids
                for page in self._paginate(
                    api,
                    f"/spaces/{space_id}/pages",
                    {"status": "current", "sort": "id"},
                )
            )
        else:
            pages = bounded(
                self._paginate(api, "/pages", {"status": "current", "sort": "id"})
            )
        if config.label_ids:
            labeled = None
            for label_id in config.label_ids:
                ids = {
                    str(value.get("id"))
                    for value in bounded(
                        self._paginate(api, f"/labels/{label_id}/pages")
                    )
                }
                labeled = ids if labeled is None else labeled & ids
            pages = [
                page for page in pages if str(page.get("id")) in (labeled or set())
            ]
        return pages

    def _discover_all(self, parsed, api):
        pages = self._selected_pages(parsed, api)
        self._pages = {}
        outcomes = []
        for page in sorted(pages, key=lambda value: int(value.get("id", 0))):
            try:
                item = _page_item(page, self.site)
            except (KeyError, ValueError, TypeError):
                outcomes.append(
                    ConfluencePreviewOutcome(
                        None,
                        "Invalid Confluence page",
                        None,
                        None,
                        None,
                        "failed",
                        "Confluence returned an invalid page identity or version.",
                        error_code="invalid_page",
                    )
                )
                continue
            if item.external_id in self._pages:
                outcomes.append(
                    ConfluencePreviewOutcome(
                        item.external_id,
                        item.display_name,
                        item.canonical_location,
                        item.provider_revision,
                        item.media_type,
                        "duplicate",
                        "Confluence page was discovered more than once.",
                    )
                )
                continue
            self._pages[item.external_id] = page
            title = item.display_name
            included = str(page.get("status", "current")) == "current"
            reason = "Confluence page is current and ready to ingest."
            if parsed.title_prefixes and not any(
                title.startswith(value) for value in parsed.title_prefixes
            ):
                included, reason = (
                    False,
                    "Confluence page title does not match an included prefix.",
                )
            if any(title.startswith(value) for value in parsed.exclude_title_prefixes):
                included, reason = (
                    False,
                    "Confluence page title matches an excluded prefix.",
                )
            outcomes.append(
                ConfluencePreviewOutcome(
                    item.external_id,
                    title,
                    item.canonical_location,
                    item.provider_revision,
                    item.media_type,
                    "included" if included else "excluded",
                    reason,
                )
            )
        return outcomes

    def discover_all(self, config):
        parsed = ConfluenceConfig.model_validate(config)
        client, api = self._api(parsed)
        try:
            return self._discover_all(parsed, api)
        finally:
            if getattr(client, "close", None):
                client.close()

    def discover(self, config, cursor=None):
        if cursor is not None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="invalid_cursor",
                    message="Confluence cursors are managed inside bounded discovery.",
                    retryable=False,
                )
            )
        outcomes = self.discover_all(config)
        return DiscoveryPage(
            items=tuple(
                _page_item(self._pages[value.external_id], self.site)
                for value in outcomes
                if value.status == "included" and value.external_id
            )
        )

    def _fetch(self, parsed, item, api):
        page = api.request(
            f"/pages/{item.external_id}",
            params={"body-format": "storage", "include-version": "true"},
        )
        current = _page_item(page, self.site)
        if current.provider_revision != item.provider_revision:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="page_changed",
                    message="The Confluence page changed after discovery. Retry the run.",
                    retryable=True,
                )
            )
        storage = ((page.get("body") or {}).get("storage") or {}).get("value")
        if not isinstance(storage, str):
            raise ConnectorFailure(
                ConnectorIssue(
                    code="unsupported_body",
                    message="Confluence did not return a supported storage-format body.",
                    retryable=False,
                )
            )
        parser = _StorageParser()
        parser.feed(storage)
        segments = parser.finish()
        content = "\n".join(segment.text for segment in segments).encode()
        if not content:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="empty_page",
                    message="The Confluence page contains no supported text.",
                    retryable=False,
                )
            )
        if len(content.decode()) > parsed.max_text_chars:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="text_limit_exceeded",
                    message="Confluence content exceeded the configured text limit.",
                    retryable=False,
                )
            )
        return ConfluenceArtifact(
            item=item,
            content=content,
            content_hash=hashlib.sha256(content).hexdigest(),
            segments=segments,
            fetched_at=self.clock(),
        )

    def fetch(self, config, item):
        parsed = ConfluenceConfig.model_validate(config)
        client, api = self._api(parsed)
        try:
            return self._fetch(parsed, item, api)
        finally:
            if getattr(client, "close", None):
                client.close()

    def fetch_all(self, config, priors, processing_config_hash):
        parsed = ConfluenceConfig.model_validate(config)
        client, api = self._api(parsed)
        try:
            outcomes = self._discover_all(parsed, api)
            artifacts = []
            for outcome in outcomes:
                if outcome.status != "included" or not outcome.external_id:
                    continue
                item = _page_item(self._pages[outcome.external_id], self.site)
                prior = priors.get(item.canonical_location)
                if (
                    prior is not None
                    and prior.provider_revision == item.provider_revision
                    and prior.processing_config_hash == processing_config_hash
                ):
                    artifacts.append(
                        ConfluenceArtifact(
                            item, None, prior.content_hash, (), self.clock(), True
                        )
                    )
                else:
                    artifacts.append(self._fetch(parsed, item, api))
            return outcomes, artifacts
        finally:
            if getattr(client, "close", None):
                client.close()
