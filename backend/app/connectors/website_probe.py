"""Small, bounded probe of a website for recommended settings (spec 0011).

`website-probe-v1` reads robots.txt and the start page of the entered site,
through the same SSRF-safe client and `WebsiteConnector.crawl()` that previews
and runs use. It returns measurements only: URLs without query strings,
counts, statuses and timings. Page bodies are dropped once the signals are
computed, and nothing the site says can widen the origins probed.

Slice 1 supports crawl input (steps robots and start_page); sitemap and sample
page steps arrive with the full rule set.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from ipaddress import ip_address
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.connectors.base import ConnectorFailure
from app.connectors.safe_http import SafeHttpClient, canonical_url, failure, url_origin
from app.connectors.website import (
    MAX_PAGE_LINKS,
    MemoryCrawlStore,
    WebsiteConnector,
    _Links,
    strip_tracking,
)
from app.schemas.ingestion import WebsiteFetchPolicy

# Bounds of one probe, enforced below whatever the connector or site does.
MAX_REQUESTS = 18
MIN_REQUEST_INTERVAL_SECONDS = 1.0
DEADLINE_SECONDS = 90.0
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 30 * 1024 * 1024
REDIRECT_LIMIT = 5
MAX_ROBOTS_SITEMAPS = 2
MAX_SIGNALS_BYTES = 64 * 1024
MAX_RECORDED_URL_CHARS = 500
THROTTLE_STATUSES = frozenset({429, 503})


class ProbeStopped(Exception):
    """Raised by `on_step` when the job was cancelled or replaced."""


def _without_query(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[
        :MAX_RECORDED_URL_CHARS
    ]


def _decoded_path(url: str) -> str:
    return unquote(urlsplit(url).path or "/")


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _is_ip(host: str) -> bool:
    try:
        ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def same_site(entered_origin: str, other_origin: str) -> bool:
    """Hosts equal after stripping one leading `www.`; scheme kept or http→https."""
    entered, other = urlsplit(entered_origin), urlsplit(other_origin)
    if not entered.hostname or not other.hostname:
        return False
    if _strip_www(entered.hostname) != _strip_www(other.hostname):
        return False
    if entered.scheme == other.scheme:
        return entered.port == other.port
    # Only an upgrade to HTTPS on default ports counts as the same site.
    return (
        entered.scheme == "http"
        and other.scheme == "https"
        and entered.port is None
        and other.port is None
    )


def same_site_origins(entered_origin: str) -> list[str]:
    """Every origin `same_site` accepts for the entered origin, entered first."""
    parts = urlsplit(entered_origin)
    host = parts.hostname or ""
    hosts = [host]
    if not _is_ip(host) and "." in host:
        hosts.append(host[4:] if host.startswith("www.") else f"www.{host}")
    netloc_port = f":{parts.port}" if parts.port is not None else ""
    origins = [entered_origin]
    for candidate in hosts:
        origins.append(f"{parts.scheme}://{candidate}{netloc_port}")
        if parts.scheme == "http" and parts.port is None:
            origins.append(f"https://{candidate}")
    return list(dict.fromkeys(origins))


@dataclass
class ProbeSignals:
    """What the probe measured. Serialized into the job's bounded `signals`."""

    probe_mode: str
    entered_url: str
    entered_origin: str
    requests: list[dict] = field(default_factory=list)
    robots: dict = field(default_factory=dict)
    start_page: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        value = asdict(self)
        encoded = json.dumps(value, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_SIGNALS_BYTES:
            # Request records are the only unbounded-ish part; keep the counts.
            value["requests"] = value["requests"][:MAX_REQUESTS]
            for item in value["requests"]:
                item["url"] = item["url"][:120]
        return value

    @classmethod
    def from_json(cls, value: dict) -> "ProbeSignals":
        return cls(**value)


class _ProbeTransport:
    """Wraps the HTTP transport: one place that counts, paces and records
    every request the probe makes, including redirect hops inside crawl()."""

    def __init__(self, inner, *, clock, sleeper, deadline: float):
        self.inner = inner
        self.clock = clock
        self.sleeper = sleeper
        self.deadline = deadline
        self.purpose = "robots"
        self.count = 0
        self.total_bytes = 0
        self.records: list[dict] = []
        self.intervals: dict[str, float] = {}
        self._last: dict[str, float] = {}

    def request(self, url, address, timeout, headers, max_bytes):
        if self.count >= MAX_REQUESTS:
            raise failure(
                "probe_request_limit",
                f"The site check reached its limit of {MAX_REQUESTS} requests.",
            )
        origin = url_origin(url)
        interval = max(MIN_REQUEST_INTERVAL_SECONDS, self.intervals.get(origin, 0.0))
        current = self.clock()
        previous = self._last.get(origin)
        slot = current if previous is None else max(current, previous + interval)
        if slot >= self.deadline:
            raise failure(
                "deadline_exceeded", "The site check exceeded its time limit."
            )
        if slot > current:
            self.sleeper(slot - current)
        self._last[origin] = slot
        remaining = MAX_TOTAL_BYTES - self.total_bytes
        if remaining <= 0:
            raise failure(
                "total_bytes_exceeded", "The site check exceeded its byte limit."
            )
        self.count += 1
        started = self.clock()
        record = {"purpose": self.purpose, "url": _without_query(url)}
        try:
            status, response_headers, body = self.inner.request(
                url,
                address,
                min(timeout, REQUEST_TIMEOUT_SECONDS),
                headers,
                min(max_bytes, MAX_RESPONSE_BYTES, remaining),
            )
        except ConnectorFailure as exc:
            record.update(
                status=None,
                outcome=exc.issue.code,
                elapsed_ms=int((self.clock() - started) * 1000),
            )
            self.records.append(record)
            raise
        self.total_bytes += len(body)
        record.update(
            status=status,
            outcome="response",
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        self.records.append(record)
        return status, response_headers, body


def _robots(
    client: SafeHttpClient,
    transport: _ProbeTransport,
    origin: str,
    start_url: str,
    allowed: set[str],
    user_agent: str,
) -> dict:
    response = client.get(
        origin + "/robots.txt",
        user_agent=user_agent,
        request_timeout=REQUEST_TIMEOUT_SECONDS,
        # The client measures its deadline on the real monotonic clock.
        deadline=time.monotonic() + max(0.0, transport.deadline - transport.clock()),
        redirect_limit=REDIRECT_LIMIT,
        max_response_bytes=MAX_RESPONSE_BYTES,
        max_total_bytes=MAX_TOTAL_BYTES - transport.total_bytes,
        allowed=lambda url: url_origin(url) in allowed,
    )
    if response.status == 404:
        return {
            "found": False,
            "status": 404,
            "crawl_delay": None,
            "start_allowed": True,
            "sitemaps": [],
        }
    if not 200 <= response.status < 300:
        # The crawl treats this the same way: no page may be fetched.
        raise failure(
            "robots_unavailable",
            f"robots.txt could not be checked safely (HTTP {response.status}).",
        )
    parser = RobotFileParser()
    parser.set_url(response.url)
    parser.parse(response.content.decode("utf-8", errors="replace").splitlines())
    delay = parser.crawl_delay(user_agent)
    sitemaps = []
    for value in parser.site_maps() or []:
        try:
            url = canonical_url(value)
        except ConnectorFailure:
            continue
        if url_origin(url) == origin and len(sitemaps) < MAX_ROBOTS_SITEMAPS:
            sitemaps.append(_without_query(url))
    return {
        "found": True,
        "status": response.status,
        "crawl_delay": float(delay) if delay else None,
        "start_allowed": parser.can_fetch(user_agent, start_url),
        "sitemaps": sitemaps,
    }


def _page_links(content: bytes, final_url: str) -> tuple[list[str], int]:
    """Canonical page links (as the connector reads them) and the text length."""
    parser = _Links(MAX_PAGE_LINKS)
    parser.feed(content.decode("utf-8", errors="replace"))
    links = []
    for href in parser.links:
        absolute = urljoin(final_url, href)
        if urlsplit(absolute).scheme.lower() not in ("http", "https"):
            continue
        try:
            links.append(strip_tracking(canonical_url(absolute)))
        except ConnectorFailure:
            continue
    return list(dict.fromkeys(links)), len(parser.text())


def probe_website(
    selection,
    *,
    connector_factory=None,
    client: SafeHttpClient | None = None,
    on_step: Callable[[str, int], None] | None = None,
    user_agent: str,
    clock=time.monotonic,
    sleeper=time.sleep,
) -> ProbeSignals:
    """Probe the site of a crawl `selection` (a dict or WebsiteSelection).

    Raises ConnectorFailure with a safe message when the site cannot be
    analysed (blocked destination, robots.txt, HTTP errors, limits).
    """
    selection = (
        selection if isinstance(selection, dict) else selection.model_dump(mode="json")
    )
    if selection.get("mode") != "crawl":
        raise failure(
            "unsupported_input",
            "Recommendations currently analyse crawl start pages only.",
        )
    start_url = canonical_url(selection["start_url"])
    entered_origin = url_origin(start_url)
    allowed = same_site_origins(entered_origin)
    allowed_set = set(allowed)
    step = on_step or (lambda name, progress: None)

    # The module attribute is read at call time, so a test stack can replace it.
    connector = (connector_factory or WebsiteConnector)()
    base = client or connector.client
    transport = _ProbeTransport(
        base.transport,
        clock=clock,
        sleeper=sleeper,
        deadline=clock() + DEADLINE_SECONDS,
    )
    probe_client = SafeHttpClient(resolver=base.resolver, transport=transport)
    connector.client = probe_client
    signals = ProbeSignals(
        probe_mode="crawl", entered_url=start_url, entered_origin=entered_origin
    )

    step("robots", 10)
    transport.purpose = "robots"
    signals.robots = _robots(
        probe_client, transport, entered_origin, start_url, allowed_set, user_agent
    )
    if signals.robots["crawl_delay"]:
        transport.intervals[entered_origin] = signals.robots["crawl_delay"]
    if not signals.robots["start_allowed"]:
        raise failure(
            "robots_blocks_start",
            "robots.txt disallows the start URL, so the site was not analysed.",
        )

    step("start_page", 40)
    transport.purpose = "start_page"
    remaining = transport.deadline - clock()
    if remaining < 1:
        raise failure("deadline_exceeded", "The site check exceeded its time limit.")
    policy = WebsiteFetchPolicy(
        policy_version=3,
        max_pages=1,
        max_depth=0,
        requests_per_second=1,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        max_response_bytes=MAX_RESPONSE_BYTES,
        max_total_bytes=MAX_TOTAL_BYTES,
        redirect_limit=REDIRECT_LIMIT,
        user_agent=user_agent,
        deadline_seconds=round(remaining, 3),
        retry_attempts=1,
        fetch_concurrency=1,
    )
    store = MemoryCrawlStore()
    connector.crawl(
        {
            "kind": "website",
            "selection": {"mode": "single_url", "url": start_url},
            "allowed_origins": allowed,
            "max_pages": 1,
            "max_depth": 0,
            "requests_per_second": 1,
        },
        policy,
        None,
        store,
    )
    signals.requests = transport.records[:MAX_REQUESTS]

    # Page requests of the start_page step; the crawl's own robots.txt read
    # is not a page response.
    page_records = [
        item
        for item in transport.records
        if item["purpose"] == "start_page"
        and item["status"] is not None
        and not item["url"].endswith("/robots.txt")
    ]
    page = store.outcomes[0] if store.outcomes else None
    if page is None:
        raise failure("start_not_fetched", "The start page could not be fetched.")
    start = {
        "status": None,
        "outcome": page.status,
        "final_url": start_url,
        "media_type": page.media_type,
        "text_length": None,
        "links_same_origin": 0,
        "links_below_path": 0,
        "response_ms": [item["elapsed_ms"] for item in page_records],
        "throttled": sum(
            1 for item in transport.records if item["status"] in THROTTLE_STATUSES
        ),
    }
    if page_records:
        start["status"] = page_records[-1]["status"]
    if page.status == "failed" and page.error_code == "outside_scope":
        # A redirect left the site. Nothing is added; the rules use the
        # entered address and the card says why.
        signals.warnings.append("redirect_other_site")
    elif page.status == "excluded" and "robots.txt" in page.reason:
        raise failure("robots_blocks_start", page.reason)
    elif page.status == "failed":
        raise failure(page.error_code or "start_not_fetched", page.reason)
    elif page.status in ("included", "duplicate"):
        final_url = page.canonical_location or start_url
        if url_origin(final_url) not in allowed_set or not same_site(
            entered_origin, url_origin(final_url)
        ):
            final_url = start_url
        start["final_url"] = final_url
        artifact = next(
            (item for item in store.artifacts if item.canonical_location == final_url),
            store.artifacts[0] if store.artifacts else None,
        )
        if artifact is not None and artifact.media_type == "text/html":
            links, text_length = _page_links(artifact.content, final_url)
            final_origin = url_origin(final_url)
            path = _decoded_path(final_url)
            same_origin = [link for link in links if url_origin(link) == final_origin]
            start["text_length"] = text_length
            start["links_same_origin"] = len(same_origin)
            start["links_below_path"] = (
                sum(
                    1
                    for link in same_origin
                    if _decoded_path(link).startswith(path.rstrip("/") + "/")
                )
                if path not in ("", "/")
                else 0
            )
        # Bodies are not kept beyond this point (spec 0011, D7).
        store.artifacts.clear()
    start["response_ms"] = start["response_ms"][:MAX_REQUESTS]
    if start["response_ms"]:
        start["median_response_ms"] = int(statistics.median(start["response_ms"]))
    else:
        start["median_response_ms"] = None
    signals.start_page = start
    return signals
