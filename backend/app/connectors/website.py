"""Bounded, non-executing Website discovery for source previews."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from app.connectors.base import ConnectorFailure
from app.connectors.safe_http import SafeHttpClient, canonical_url, failure, url_origin
from app.schemas.ingestion import WebsiteConfig


@dataclass(frozen=True)
class PreviewOutcome:
    external_id: str | None
    display_name: str
    canonical_location: str | None
    media_type: str | None
    status: str
    reason: str
    size_bytes: int | None = None
    depth: int | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class PriorWebsiteRevision:
    content: bytes
    media_type: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class WebsiteArtifact:
    canonical_location: str
    content: bytes
    media_type: str
    etag: str | None
    last_modified: str | None
    validator_unchanged: bool
    depth: int


class _Links(HTMLParser):
    def __init__(self, limit: int):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() not in ("a", "area") or len(self.links) >= self.limit:
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)
                return


def _media_type(headers: dict[str, str]) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


class WebsiteConnector:
    kind = "website"
    config_version = "1"

    def __init__(
        self,
        *,
        client: SafeHttpClient | None = None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        self.client = client or SafeHttpClient()
        self.clock = clock
        self.sleeper = sleeper

    def validate(self, config: object, connection: object | None) -> None:
        if connection is not None:
            raise failure(
                "connection_not_supported",
                "Public Website sources do not use credentials.",
            )
        WebsiteConfig.model_validate(config)

    def test_connection(self, connection: object | None):
        raise failure(
            "test_not_supported", "Preview the Website source to test public access."
        )

    @staticmethod
    def _scope(config: WebsiteConfig):
        origins = {url_origin(str(value)) for value in config.allowed_origins}

        def origin_allowed(url: str):
            return url_origin(url) in origins

        def page_allowed(url: str):
            if not origin_allowed(url):
                return False
            path = unquote(urlsplit(url).path or "/")
            if config.include_path_prefixes and not any(
                path.startswith(prefix) for prefix in config.include_path_prefixes
            ):
                return False
            return not any(
                path.startswith(prefix) for prefix in config.exclude_path_prefixes
            )

        return origin_allowed, page_allowed

    def _discover(
        self,
        config: object,
        priors: dict[str, PriorWebsiteRevision] | None = None,
    ) -> tuple[list[PreviewOutcome], list[WebsiteArtifact]]:
        parsed = WebsiteConfig.model_validate(config)
        priors = priors or {}
        origin_allowed, page_allowed = self._scope(parsed)
        deadline = self.clock() + parsed.deadline_seconds
        transferred = 0
        last_request = 0.0
        robots: dict[str, RobotFileParser | None] = {}

        def request(url: str, *, page_scope=True, validators=None):
            nonlocal transferred, last_request
            delay = 1 / parsed.requests_per_second - (self.clock() - last_request)
            if delay > 0:
                self.sleeper(delay)
            response = self.client.get(
                url,
                user_agent=parsed.user_agent,
                request_timeout=parsed.request_timeout_seconds,
                deadline=deadline,
                redirect_limit=parsed.redirect_limit,
                max_response_bytes=parsed.max_response_bytes,
                max_total_bytes=parsed.max_total_bytes - transferred,
                allowed=page_allowed if page_scope else origin_allowed,
                request_headers=validators,
            )
            last_request = self.clock()
            transferred += response.transferred_bytes
            return response

        def robots_allowed(url: str):
            if not parsed.respect_robots:
                return True
            origin = url_origin(url)
            if origin not in robots:
                response = request(origin + "/robots.txt", page_scope=False)
                if response.status == 404:
                    robots[origin] = None
                elif 200 <= response.status < 300:
                    parser = RobotFileParser()
                    parser.set_url(response.url)
                    parser.parse(
                        response.content.decode("utf-8", errors="replace").splitlines()
                    )
                    robots[origin] = parser
                else:
                    raise failure(
                        "robots_unavailable",
                        "robots.txt could not be checked safely.",
                        retryable=response.status >= 500,
                    )
            policy = robots[origin]
            return policy is None or policy.can_fetch(parsed.user_agent, url)

        selection = parsed.selection
        crawl = selection.mode == "crawl"
        if selection.mode == "single_url":
            seeds = [(str(selection.url), 0)]
        elif selection.mode == "url_list":
            seeds = [(str(url), 0) for url in selection.urls]
        elif crawl:
            seeds = [(str(selection.start_url), 0)]
        else:
            response = request(str(selection.sitemap_url), page_scope=False)
            if not 200 <= response.status < 300:
                raise failure(
                    "sitemap_request_failed",
                    "The sitemap could not be fetched.",
                    retryable=response.status >= 500,
                )
            media = _media_type(response.headers)
            if media not in ("application/xml", "text/xml", "application/rss+xml"):
                raise failure(
                    "unsupported_sitemap", "The sitemap response must be XML."
                )
            if (
                b"<!DOCTYPE" in response.content.upper()
                or b"<!ENTITY" in response.content.upper()
            ):
                raise failure(
                    "unsafe_sitemap",
                    "Sitemaps with document types or entities are not accepted.",
                )
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError as exc:
                raise failure(
                    "invalid_sitemap", "The sitemap XML is malformed."
                ) from exc
            seeds = [
                ((element.text or "").strip(), 0)
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].lower() == "loc"
                and (element.text or "").strip()
            ]

        outcomes: list[PreviewOutcome] = []
        artifacts: list[WebsiteArtifact] = []
        queue = list(seeds)
        seen: set[str] = set()
        duplicate_reported: set[str] = set()
        fetched_pages = 0
        discovery_limit = min(4000, parsed.max_pages * 4)

        def record(
            url, status, reason, *, media=None, size=None, depth=None, code=None
        ):
            outcomes.append(
                PreviewOutcome(
                    external_id=url,
                    display_name=url,
                    canonical_location=url,
                    media_type=media,
                    status=status,
                    reason=reason,
                    size_bytes=size,
                    depth=depth,
                    error_code=code,
                )
            )

        while queue and len(outcomes) < discovery_limit:
            raw_url, depth = queue.pop(0)
            try:
                url = canonical_url(raw_url)
            except ConnectorFailure as exc:
                record(
                    None, "failed", exc.issue.message, depth=depth, code=exc.issue.code
                )
                continue
            if url in seen:
                if url not in duplicate_reported:
                    record(
                        url,
                        "duplicate",
                        "Duplicate canonical URL; fetched only once.",
                        depth=depth,
                    )
                    duplicate_reported.add(url)
                continue
            seen.add(url)
            if not origin_allowed(url):
                record(
                    url,
                    "excluded",
                    "URL origin is outside the configured allowlist.",
                    depth=depth,
                )
                continue
            if not page_allowed(url):
                record(
                    url,
                    "excluded",
                    "URL path is outside the configured include/exclude rules.",
                    depth=depth,
                )
                continue
            if depth > parsed.max_depth:
                record(
                    url,
                    "excluded",
                    "URL exceeds the configured crawl depth.",
                    depth=depth,
                )
                continue
            if fetched_pages >= parsed.max_pages:
                record(
                    url,
                    "excluded",
                    "URL exceeds the configured page limit.",
                    depth=depth,
                )
                continue
            try:
                if not robots_allowed(url):
                    record(
                        url, "excluded", "robots.txt disallows this URL.", depth=depth
                    )
                    continue
                prior = priors.get(url)
                validators = {}
                if prior and prior.etag:
                    validators["If-None-Match"] = prior.etag
                if prior and prior.last_modified:
                    validators["If-Modified-Since"] = prior.last_modified
                response = request(url, validators=validators)
                validator_unchanged = response.status == 304
                if validator_unchanged and prior is None:
                    raise failure(
                        "invalid_not_modified",
                        "Website returned not-modified without a prior revision.",
                    )
                if response.status != 304 and not 200 <= response.status < 300:
                    record(
                        url,
                        "failed",
                        f"Website returned HTTP {response.status}.",
                        depth=depth,
                        code="http_status",
                    )
                    continue
                media = (
                    prior.media_type
                    if validator_unchanged
                    else _media_type(response.headers)
                )
                if media != "text/html":
                    record(
                        response.url,
                        "excluded",
                        "Only HTML pages are supported in Website preview.",
                        media=media or None,
                        size=len(
                            prior.content if validator_unchanged else response.content
                        ),
                        depth=depth,
                    )
                    continue
                fetched_pages += 1
                content = prior.content if validator_unchanged else response.content
                record(
                    response.url,
                    "included",
                    "HTML page is within scope and fetchable.",
                    media=media,
                    size=len(content),
                    depth=depth,
                )
                artifacts.append(
                    WebsiteArtifact(
                        canonical_location=response.url,
                        content=content,
                        media_type=media,
                        etag=response.headers.get("etag")
                        or (prior.etag if prior else None),
                        last_modified=response.headers.get("last-modified")
                        or (prior.last_modified if prior else None),
                        validator_unchanged=validator_unchanged,
                        depth=depth,
                    )
                )
                if crawl and depth < parsed.max_depth:
                    parser = _Links(max(0, discovery_limit - len(outcomes)))
                    parser.feed(content.decode("utf-8", errors="replace"))
                    queue.extend(
                        (urljoin(response.url, link), depth + 1)
                        for link in parser.links
                    )
            except ConnectorFailure as exc:
                record(
                    url, "failed", exc.issue.message, depth=depth, code=exc.issue.code
                )

        if queue:
            record(
                None, "excluded", "Additional URLs were omitted by the discovery limit."
            )
        return outcomes, artifacts

    def discover_all(self, config: object) -> list[PreviewOutcome]:
        return self._discover(config)[0]

    def fetch_all(
        self,
        config: object,
        priors: dict[str, PriorWebsiteRevision] | None = None,
    ) -> tuple[list[PreviewOutcome], list[WebsiteArtifact]]:
        return self._discover(config, priors)

    def discover(self, config: object, cursor: str | None = None):
        raise failure(
            "async_only", "Website discovery runs through an asynchronous preview job."
        )

    def fetch(self, item, prior_revision=None):
        raise failure(
            "preview_only", "Website ingestion is introduced in the next phase."
        )
