"""Small, bounded probe of a website for recommended settings (spec 0011).

`website-probe-v1` reads robots.txt, the start page, the site's sitemap and a
few linked pages, through the same SSRF-safe client and
`WebsiteConnector.crawl()` that previews and runs use. It returns
measurements only: URLs without query strings, path sections, counts,
statuses and timings. Page bodies are dropped once the signals are computed,
and nothing the site says can widen the origins probed.

Steps per input: crawl and single page run robots and start_page (crawl also
sitemaps and sample_pages); a sitemap runs robots and sitemaps; a URL list runs
robots and start_page for its first origins.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from app.connectors.base import ConnectorFailure
from app.connectors.safe_http import SafeHttpClient, canonical_url, failure, url_origin
from app.connectors.website import (
    MAX_PAGE_LINKS,
    MemoryCrawlStore,
    WebsiteConnector,
    _Links,
    _child_text,
    _local_name,
    parse_robots,
    parse_sitemap_response,
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
MAX_TOP_SITEMAPS = 3
MAX_NESTED_SITEMAPS = 3
MAX_SAMPLE_PAGES = 9
MAX_URL_LIST_ROBOTS = 5
MAX_URL_LIST_PAGES = 3
MAX_SIGNALS_BYTES = 64 * 1024
MAX_RECORDED_URL_CHARS = 500
MAX_RECORDED_PATH_CHARS = 200
MAX_SECTIONS = 60
MAX_SECTION_SAMPLES = 3
MAX_HREFLANG = 40
# A <loc> list longer than the sitemap protocol allows is not read further.
MAX_SITEMAP_LOCS = 50_000
THROTTLE_STATUSES = frozenset({429, 503})
# Request outcomes that end the probe's remaining requests.
EXHAUSTED = frozenset(
    {"probe_request_limit", "deadline_exceeded", "total_bytes_exceeded"}
)
# Links that are not pages; sampling them would spend requests on downloads.
SKIPPED_EXTENSIONS = (
    ".pdf", ".zip", ".gz", ".tgz", ".tar", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".webp", ".ico", ".mp3", ".mp4", ".webm", ".avi", ".mov", ".exe",
    ".dmg", ".iso", ".xml", ".json", ".csv", ".txt", ".epub", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx",
)  # fmt: skip
# utility-paths-v1: path segments that never hold content worth indexing.
UTILITY_SEGMENTS = frozenset(
    {
        "search",
        "login",
        "signin",
        "sign-in",
        "logout",
        "cart",
        "checkout",
        "feed",
        "rss",
        "wp-admin",
        "wp-json",
        "print",
    }
)


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


def folder_prefix(path: str) -> list[str]:
    """Today's derived include prefix: `/docs/x` → `/docs/`; none for `/`."""
    directory = path[: path.rfind("/") + 1]
    return [directory] if directory and directory != "/" else []


def include_scope(
    entered_url: str, final_url: str, links_same_origin: int, links_below_path: int
) -> tuple[list[str], str, dict]:
    """The include rule: (prefixes, reason code, reason values).

    If the final path ends with `/` it is the prefix. Otherwise, when at least
    half of the start page's same-origin links are below `path + "/"`, that is
    the prefix; else the path's parent folder. A root path gives none. The
    prefix never starts outside today's derivation from the entered or the
    final URL, so it is never wider than today; if it would, today's value is
    returned with `default_no_evidence`. The probe counts and samples within
    this scope, and the rules recommend it.
    """
    entered_path = _decoded_path(entered_url)
    path = _decoded_path(final_url)
    if path in ("", "/"):
        value, code, context = [], "include_none", {}
    elif path.endswith("/"):
        value = [path]
        code = "include_redirect_folder" if path != entered_path else "include_folder"
        context = {"entered_path": entered_path, "prefix": path}
    elif links_same_origin > 0 and links_below_path >= 0.5 * links_same_origin:
        prefix = path + "/"
        value, code = [prefix], "include_links_folder"
        context = {
            "below": links_below_path,
            "total": links_same_origin,
            "prefix": prefix,
        }
    else:
        value = folder_prefix(path)
        code = "include_folder" if value else "include_none"
        context = {"prefix": value[0]} if value else {}
    bases = [(folder_prefix(entered_path) or [""])[0], (folder_prefix(path) or [""])[0]]
    narrowest = value[0] if value else ""
    if not any(narrowest.startswith(base) for base in bases):
        return folder_prefix(entered_path), "default_no_evidence", {}
    return value, code, context


def section_of(path: str, include: list[str]) -> str | None:
    """The path segment one level below the include prefix (or the first
    segment when there is none); None for the prefix's own page."""
    base = include[0] if include else "/"
    if not path.startswith(base):
        return None
    segment = path[len(base) :].split("/", 1)[0]
    return segment or None


def section_prefix(segment: str, include: list[str], exact: bool) -> str:
    """The exclusion prefix of a section: with a trailing slash unless the
    section's own page was linked without one (`/es` redirecting to `/es/`)."""
    base = include[0] if include else "/"
    return base + segment + ("" if exact else "/")


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
    # robots.txt facts of other origins: a same-site redirect target, or the
    # first origins of a URL list.
    extra_robots: list[dict] = field(default_factory=list)
    # The include prefixes the probe counted and sampled within.
    scope_prefixes: list[str] = field(default_factory=list)
    start_section: str | None = None
    sitemap: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    # In-scope URLs per section one level below the scope prefix.
    sections: list[dict] = field(default_factory=list)
    sample_pages: list[dict] = field(default_factory=list)
    url_list: dict = field(default_factory=dict)
    timing: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        """The signals within MAX_SIGNALS_BYTES; detail goes before counts."""
        value = asdict(self)
        shrinks = (
            _drop_section_samples,
            _drop_hreflang,
            _shorten_urls,
            _trim_sections,
            _drop_detail,
        )
        for shrink in shrinks:
            if _size(value) <= MAX_SIGNALS_BYTES:
                break
            shrink(value)
        return value

    @classmethod
    def from_json(cls, value: dict) -> "ProbeSignals":
        return cls(**value)


def _size(value) -> int:
    return len(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _drop_section_samples(value: dict) -> None:
    for section in value["sections"]:
        section["samples"] = []


def _drop_hreflang(value: dict) -> None:
    value["start_page"].pop("hreflang", None)


def _shorten_urls(value: dict) -> None:
    for item in value["requests"] + value["sample_pages"]:
        item["url"] = item["url"][:120]


def _trim_sections(value: dict) -> None:
    value["sections"] = value["sections"][:20]


def _drop_detail(value: dict) -> None:
    value["sections"] = []
    value["sample_pages"] = []
    value["requests"] = [
        {"purpose": item["purpose"], "status": item.get("status")}
        for item in value["requests"]
    ]
    value["extra_robots"] = value["extra_robots"][:MAX_URL_LIST_ROBOTS]
    for robots in [value["robots"], *value["extra_robots"]]:
        robots.pop("sitemaps", None)
    value["url_list"].pop("pages", None)


class _ProbeTransport:
    """Wraps the HTTP transport: one place that counts, paces and records
    every request the probe makes, including redirect hops inside crawl().

    robots.txt responses are kept per URL, so the crawl's own robots.txt read
    of an origin the probe already checked is not a second request.
    """

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
        self._robots: dict[str, tuple] = {}

    def interval(self, origin: str) -> float:
        return max(MIN_REQUEST_INTERVAL_SECONDS, self.intervals.get(origin, 0.0))

    def request(self, url, address, timeout, headers, max_bytes):
        robots = urlsplit(url).path == "/robots.txt"
        if robots and url in self._robots:
            return self._robots[url]
        if self.count >= MAX_REQUESTS:
            raise failure(
                "probe_request_limit",
                f"The site check reached its limit of {MAX_REQUESTS} requests.",
            )
        origin = url_origin(url)
        current = self.clock()
        previous = self._last.get(origin)
        slot = (
            current
            if previous is None
            else max(current, previous + self.interval(origin))
        )
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
        if robots:
            self._robots[url] = (status, response_headers, body)
        return status, response_headers, body

    def timing(self) -> dict:
        """Response times of page and sitemap requests, and throttling seen."""
        times = [
            item["elapsed_ms"]
            for item in self.records
            if item["status"] is not None and item["purpose"] != "robots"
        ]
        return {
            "median_response_ms": int(statistics.median(times)) if times else None,
            "throttled": sum(
                1 for item in self.records if item["status"] in THROTTLE_STATUSES
            ),
        }


class _PageFacts(HTMLParser):
    """`<html lang>`, `<link rel=alternate hreflang>` and the first
    `<link rel=canonical>` of a page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.alternates: list[tuple[str, str]] = []
        self.canonical: str | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        values = {key.lower(): value for key, value in attrs if value}
        if tag == "html" and self.lang is None and values.get("lang"):
            self.lang = values["lang"].strip()[:35]
        elif (
            tag == "link"
            and "alternate" in (values.get("rel") or "").lower().split()
            and values.get("hreflang")
            and values.get("href")
            and len(self.alternates) < MAX_HREFLANG
        ):
            self.alternates.append((values["hreflang"].strip()[:35], values["href"]))
        elif (
            tag == "link"
            and self.canonical is None
            and "canonical" in (values.get("rel") or "").lower().split()
            and values.get("href")
        ):
            self.canonical = values["href"]


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


def _client_rendered(artifact) -> bool:
    # Imported here: the ingestion service loads persistence modules that the
    # connector package does not otherwise need.
    from app.services.website_ingestion import page_warnings

    return bool(page_warnings(artifact))


def _probe_policy(
    user_agent: str, remaining: float, pages: int = 1
) -> WebsiteFetchPolicy:
    return WebsiteFetchPolicy(
        policy_version=3,
        max_pages=pages,
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


class _Probe:
    """State of one probe run; every request goes through `transport`."""

    def __init__(self, connector, client, transport, user_agent, clock, step):
        self.connector = connector
        self.client = client
        self.transport = transport
        self.user_agent = user_agent
        self.clock = clock
        self.step = step
        self.rules: dict[str, object] = {}

    # Requests ---------------------------------------------------------------

    def remaining(self) -> float:
        return self.transport.deadline - self.clock()

    def get(self, url: str, allowed: set[str], *, gzip: bool = False):
        return self.client.get(
            url,
            user_agent=self.user_agent,
            request_timeout=REQUEST_TIMEOUT_SECONDS,
            # The client measures its deadline on the real monotonic clock.
            deadline=time.monotonic() + max(0.0, self.remaining()),
            redirect_limit=REDIRECT_LIMIT,
            max_response_bytes=MAX_RESPONSE_BYTES,
            max_total_bytes=MAX_TOTAL_BYTES - self.transport.total_bytes,
            allowed=lambda value: url_origin(value) in allowed,
            allow_gzip_encoding=gzip,
        )

    def robots(self, origin: str, allowed: set[str], check_url: str | None) -> dict:
        """robots.txt facts of one origin; its Crawl-delay paces the probe."""
        self.transport.purpose = "robots"
        response = self.get(origin + "/robots.txt", allowed)
        rules = parse_robots(response)
        self.rules[origin] = rules
        if rules is None:
            return {
                "origin": origin,
                "found": False,
                "status": response.status,
                "crawl_delay": None,
                "start_allowed": True,
                "sitemaps": [],
            }
        delay = rules.crawl_delay(self.user_agent)
        if delay:
            self.transport.intervals[origin] = delay
        sitemaps = []
        for value in rules.site_maps():
            try:
                url = canonical_url(value)
            except ConnectorFailure:
                continue
            if url_origin(url) == origin and len(sitemaps) < MAX_ROBOTS_SITEMAPS:
                sitemaps.append(url[:MAX_RECORDED_URL_CHARS])
        return {
            "origin": origin,
            "found": True,
            "status": response.status,
            "crawl_delay": delay,
            "start_allowed": (
                rules.can_fetch(self.user_agent, check_url) if check_url else True
            ),
            "sitemaps": sitemaps,
        }

    def robots_allow(self, url: str) -> bool:
        rules = self.rules.get(url_origin(url))
        return rules is None or rules.can_fetch(self.user_agent, url)

    def crawl(self, selection: dict, allowed: list[str], pages: int):
        """One connector crawl of up to `pages` listed pages; its store."""
        remaining = self.remaining()
        if remaining < 1:
            raise failure(
                "deadline_exceeded", "The site check exceeded its time limit."
            )
        store = MemoryCrawlStore()
        self.connector.crawl(
            {
                "kind": "website",
                "selection": selection,
                "allowed_origins": allowed,
                "max_pages": pages,
                "max_depth": 0,
                "requests_per_second": 1,
            },
            _probe_policy(self.user_agent, remaining, pages),
            None,
            store,
        )
        return store

    def page_records(self, purpose: str) -> list[dict]:
        """Page responses of a step; the crawl's robots.txt reads are not pages."""
        return [
            item
            for item in self.transport.records
            if item["purpose"] == purpose
            and item["status"] is not None
            and not item["url"].endswith("/robots.txt")
        ]

    # Start page -------------------------------------------------------------

    def start_page(self, start_url: str, allowed: list[str], signals: ProbeSignals):
        """Fetch the start page; returns (final URL, its links, artifact facts)."""
        self.step("start_page", 40)
        self.transport.purpose = "start_page"
        store = self.crawl({"mode": "single_url", "url": start_url}, allowed, 1)
        records = self.page_records("start_page")
        page = store.outcomes[0] if store.outcomes else None
        if page is None:
            raise failure("start_not_fetched", "The start page could not be fetched.")
        start = {
            "status": records[-1]["status"] if records else None,
            "outcome": page.status,
            "final_url": start_url,
            "media_type": page.media_type,
            "text_length": None,
            "html_lang": None,
            "hreflang": [],
            "links_total": 0,
            "links_same_origin": 0,
            "links_below_path": 0,
            "canonical_url": None,
            "response_ms": [item["elapsed_ms"] for item in records][:MAX_REQUESTS],
            "throttled": sum(
                1
                for item in self.transport.records
                if item["status"] in THROTTLE_STATUSES
            ),
        }
        links: list[str] = []
        if page.status == "failed" and page.error_code == "outside_scope":
            # A redirect left the site. Nothing is added; the rules use the
            # entered address and the card says why.
            signals.warnings.append("redirect_other_site")
        elif page.status == "excluded" and "robots.txt" in page.reason:
            raise failure("robots_blocks_start", page.reason)
        elif page.status == "excluded" and page.media_type:
            raise failure(
                "non_html_start",
                f"The address is not an HTML page ({page.media_type[:80]}).",
            )
        elif page.status == "failed":
            status = start["status"]
            if status is not None and 400 <= status < 500:
                raise failure(
                    "start_not_found", f"The start page returned HTTP {status}."
                )
            raise failure(page.error_code or "start_not_fetched", page.reason)
        elif page.status in ("included", "duplicate"):
            entered_origin = url_origin(start_url)
            final_url = page.canonical_location or start_url
            if url_origin(final_url) not in allowed or not same_site(
                entered_origin, url_origin(final_url)
            ):
                final_url = start_url
            start["final_url"] = final_url
            artifact = next(
                (
                    item
                    for item in store.artifacts
                    if item.canonical_location == final_url
                ),
                store.artifacts[0] if store.artifacts else None,
            )
            if artifact is not None and artifact.media_type == "text/html":
                links, text_length = _page_links(artifact.content, final_url)
                facts = _PageFacts()
                facts.feed(artifact.content.decode("utf-8", errors="replace"))
                final_origin = url_origin(final_url)
                path = _decoded_path(final_url)
                same_origin = [
                    link for link in links if url_origin(link) == final_origin
                ]
                start["text_length"] = text_length
                start["html_lang"] = facts.lang
                start["hreflang"] = [
                    {"lang": lang, "url": _alternate_url(href, final_url)}
                    for lang, href in facts.alternates
                ]
                # Another address of this same page (docs.python.org declares
                # .../tutorial/index.html), so links to it are not new pages.
                canonical = (
                    _alternate_url(facts.canonical, final_url)
                    if facts.canonical
                    else ""
                )
                start["canonical_url"] = (
                    canonical
                    if canonical
                    and canonical != final_url
                    and url_origin(canonical) == final_origin
                    else None
                )
                start["links_total"] = len(links)
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
                if _client_rendered(artifact):
                    signals.warnings.append("client_rendered")
                site = set(allowed)
                if links and not any(url_origin(link) in site for link in links):
                    signals.warnings.append("all_links_off_origin")
            # Bodies are not kept beyond this point (spec 0011, D7).
            store.artifacts.clear()
        start["median_response_ms"] = (
            int(statistics.median(start["response_ms"]))
            if start["response_ms"]
            else None
        )
        signals.start_page = start
        return start["final_url"], links

    # Sitemaps ---------------------------------------------------------------

    def sitemaps(
        self,
        candidates: list[tuple[str, str]],
        origins: set[str],
        include: list[str],
        *,
        required: bool,
    ) -> tuple[dict, set[str]]:
        """Read the first sitemap that parses, and up to 3 nested files.

        Returns the facts and the in-scope page URLs it lists. With `required`
        (sitemap input) a sitemap that cannot be read fails the probe.
        """
        self.step("sitemaps", 60)
        self.transport.purpose = "sitemaps"
        facts = {
            "found": False,
            "url": None,
            "source": None,
            "files_read": 0,
            "nested_listed": 0,
            "nested_read": 0,
            "nested_skipped": 0,
            "lower_bound": False,
            "in_scope": 0,
            "out_of_scope": 0,
            "linked_in_sitemap": 0,
            "errors": [],
        }
        listed: set[str] = set()
        counts = [0, 0]

        def read(url: str):
            """(final URL after redirects, parsed root)."""
            response = self.get(url, origins, gzip=True)
            return response.url, parse_sitemap_response(response, MAX_RESPONSE_BYTES)

        def count(root) -> None:
            for element in root.iter():
                if counts[0] + counts[1] >= MAX_SITEMAP_LOCS:
                    facts["lower_bound"] = True
                    return
                if _local_name(element) != "url":
                    continue
                loc = _child_text(element, "loc")
                try:
                    url = strip_tracking(canonical_url(loc))
                except ConnectorFailure:
                    counts[1] += 1
                    continue
                path = _decoded_path(url)
                if url_origin(url) in origins and (
                    not include or any(path.startswith(item) for item in include)
                ):
                    if url not in listed:
                        listed.add(url)
                        counts[0] += 1
                else:
                    counts[1] += 1

        def error(url: str, exc: ConnectorFailure) -> None:
            facts["errors"].append({"url": _without_query(url), "code": exc.issue.code})

        for source, url in candidates[:MAX_TOP_SITEMAPS]:
            try:
                final, root = read(url)
            except ConnectorFailure as exc:
                if required:
                    raise failure(
                        "sitemap_unreadable",
                        f"The sitemap could not be read. {exc.issue.message}",
                    ) from exc
                error(url, exc)
                if exc.issue.code in EXHAUSTED:
                    break
                continue
            name = _local_name(root)
            if name not in ("urlset", "sitemapindex"):
                if required:
                    raise failure(
                        "sitemap_unreadable",
                        "The sitemap could not be read. It is not a sitemap file.",
                    )
                facts["errors"].append(
                    {"url": _without_query(url), "code": "not_a_sitemap"}
                )
                continue
            facts.update(found=True, source=source, files_read=1)
            # A sitemap address with a query string is not recorded, so it
            # cannot be recommended (D7).
            if not urlsplit(final).query and len(final) <= MAX_RECORDED_URL_CHARS:
                facts["url"] = final
            if name == "urlset":
                count(root)
                break
            nested = [
                loc
                for element in root.iter()
                if _local_name(element) == "sitemap"
                and (loc := _child_text(element, "loc"))
            ]
            facts["nested_listed"] = len(nested)
            for raw in nested:
                if facts["nested_read"] >= MAX_NESTED_SITEMAPS:
                    break
                try:
                    child_url = canonical_url(raw)
                    if url_origin(child_url) not in origins:
                        raise failure(
                            "outside_scope", "The nested sitemap is on another site."
                        )
                    _, child = read(child_url)
                except ConnectorFailure as exc:
                    error(raw, exc)
                    if exc.issue.code in EXHAUSTED:
                        break
                    continue
                facts["files_read"] += 1
                if _local_name(child) == "sitemapindex":
                    # Followed only one level deep, as the connector does.
                    facts["errors"].append(
                        {"url": _without_query(child_url), "code": "nested_index"}
                    )
                    continue
                facts["nested_read"] += 1
                count(child)
            facts["nested_skipped"] = facts["nested_listed"] - facts["nested_read"]
            if facts["nested_skipped"]:
                facts["lower_bound"] = True
            break
        facts["in_scope"], facts["out_of_scope"] = counts
        facts["errors"] = facts["errors"][:10]
        return facts, listed

    # Sample pages -----------------------------------------------------------

    def sample(
        self,
        candidates: list[str],
        include: list[str],
        allowed: list[str],
        known: set[str],
        scope_origins: set[str],
    ) -> tuple[list[dict], set[str]]:
        """Fetch up to 9 linked pages round-robin across sections; returns
        their records and the new in-scope URLs they link to (L2)."""
        self.step("sample_pages", 75)
        self.transport.purpose = "sample_pages"
        sections: dict[str, list[str]] = {}
        for url in candidates:
            path = _decoded_path(url)
            if path.lower().endswith(SKIPPED_EXTENSIONS) or not self.robots_allow(url):
                continue
            sections.setdefault(section_of(path, include) or "", []).append(url)
        # Utility sections are sampled last; they are likely to be excluded.
        order = sorted(sections, key=lambda name: name in UTILITY_SEGMENTS)
        chosen: list[str] = []
        while len(chosen) < MAX_SAMPLE_PAGES and any(sections.values()):
            for name in order:
                if sections[name] and len(chosen) < MAX_SAMPLE_PAGES:
                    chosen.append(sections[name].pop(0))
        interval = max([self.transport.interval(origin) for origin in allowed] or [1.0])
        room = min(
            MAX_REQUESTS - self.transport.count,
            int((self.remaining() - 1) // interval),
        )
        chosen = chosen[: max(0, room)]
        if not chosen:
            return [], set()
        store = self.crawl({"mode": "url_list", "urls": chosen}, allowed, len(chosen))
        records = self.page_records("sample_pages")
        timings = {}
        for item in records:
            timings.setdefault(item["url"], item)
        new_links: set[str] = set()
        samples = []
        artifacts = {item.canonical_location: item for item in store.artifacts}
        for outcome in store.outcomes:
            location = outcome.canonical_location or ""
            if outcome.status == "excluded" and location not in chosen:
                # A rel=canonical target or other URL the crawl recorded itself.
                continue
            record = timings.get(_without_query(location), {})
            artifact = artifacts.get(location)
            sample = {
                "url": _without_query(location),
                "section": section_of(_decoded_path(location), include),
                "outcome": outcome.status,
                "status": record.get("status"),
                "response_ms": record.get("elapsed_ms"),
                "text_length": None,
                "new_links": 0,
            }
            if artifact is not None and artifact.media_type == "text/html":
                links, sample["text_length"] = _page_links(artifact.content, location)
                found = {
                    link
                    for link in links
                    if _in_scope(link, scope_origins, include) and link not in known
                }
                sample["new_links"] = len(found - new_links)
                new_links |= found
            samples.append(sample)
        store.artifacts.clear()
        return samples[:MAX_SAMPLE_PAGES], new_links


def _alternate_url(href: str, base: str) -> str:
    try:
        return _without_query(canonical_url(href, base=base))[:MAX_RECORDED_PATH_CHARS]
    except ConnectorFailure:
        return ""


def _in_scope(url: str, origins: set[str], include: list[str]) -> bool:
    if url_origin(url) not in origins:
        return False
    path = _decoded_path(url)
    return not include or any(path.startswith(item) for item in include)


def _sections(include: list[str], linked: set[str], listed: set[str]) -> list[dict]:
    """In-scope URLs per section: distinct URLs, by links and by sitemap."""
    base = include[0] if include else "/"
    found: dict[str, dict] = {}
    # Sorted, so the recorded sample paths do not depend on set order.
    for url in sorted(linked | listed):
        path = _decoded_path(url)
        segment = section_of(path, include)
        if segment is None:
            continue
        item = found.setdefault(
            segment,
            {
                "segment": segment[:MAX_RECORDED_PATH_CHARS],
                "count": 0,
                "links": 0,
                "sitemap": 0,
                "exact": False,
                "numbered": True,
                "samples": [],
            },
        )
        item["count"] += 1
        item["links"] += url in linked
        item["sitemap"] += url in listed
        item["exact"] |= path == base + segment
        rest = path[len(base) + len(segment) :].strip("/").split("/", 1)[0]
        item["numbered"] &= rest.isdigit()
        if len(item["samples"]) < MAX_SECTION_SAMPLES:
            item["samples"].append(path[:MAX_RECORDED_PATH_CHARS])
    ordered = sorted(found.values(), key=lambda item: (-item["count"], item["segment"]))
    return ordered[:MAX_SECTIONS]


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
    """Probe the site of a Website `selection` (a dict or WebsiteSelection).

    Raises ConnectorFailure with a safe message when the site cannot be
    analysed (blocked destination, robots.txt, HTTP errors, limits).
    """
    selection = (
        selection if isinstance(selection, dict) else selection.model_dump(mode="json")
    )
    mode = selection.get("mode")
    if mode not in ("crawl", "single_url", "sitemap", "url_list"):
        raise failure("unsupported_input", "This Website input cannot be analysed.")
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
    probe = _Probe(connector, probe_client, transport, user_agent, clock, step)
    if mode == "url_list":
        signals = _probe_url_list(probe, selection)
    elif mode == "sitemap":
        signals = _probe_sitemap(probe, selection)
    else:
        signals = _probe_page(probe, selection)
    signals.requests = transport.records[:MAX_REQUESTS]
    signals.timing = transport.timing()
    return signals


def _probe_page(probe: _Probe, selection: dict) -> ProbeSignals:
    """Crawl or single-page input: robots, start page; crawl also reads the
    sitemap and samples linked pages."""
    crawl = selection["mode"] == "crawl"
    start_url = canonical_url(selection["start_url" if crawl else "url"])
    entered_origin = url_origin(start_url)
    allowed = same_site_origins(entered_origin)
    allowed_set = set(allowed)
    signals = ProbeSignals(
        probe_mode=selection["mode"],
        entered_url=start_url,
        entered_origin=entered_origin,
    )
    probe.step("robots", 10)
    signals.robots = probe.robots(entered_origin, allowed_set, start_url)
    if not signals.robots["start_allowed"]:
        raise failure(
            "robots_blocks_start",
            "robots.txt disallows the start URL, so the site was not analysed.",
        )
    final_url, links = probe.start_page(start_url, allowed, signals)
    final_origin = url_origin(final_url)
    scope_origins = {entered_origin, final_origin}
    if final_origin != entered_origin:
        # The crawl already read this robots.txt; the transport returns it again.
        signals.extra_robots.append(probe.robots(final_origin, allowed_set, final_url))
    if not crawl:
        return signals

    start = signals.start_page
    include, _, _ = include_scope(
        start_url,
        final_url,
        start.get("links_same_origin", 0),
        start.get("links_below_path", 0),
    )
    signals.scope_prefixes = include
    signals.start_section = section_of(_decoded_path(final_url), include)
    itself = {start_url, final_url}
    if start.get("canonical_url"):
        itself.add(start["canonical_url"])
    level_one = [
        link
        for link in links
        if _in_scope(link, scope_origins, include) and link not in itself
    ]

    robots_sitemaps = [
        url for facts in [signals.robots, *signals.extra_robots]
        for url in facts.get("sitemaps", [])
    ]  # fmt: skip
    candidates = [("robots", url) for url in dict.fromkeys(robots_sitemaps)][
        :MAX_ROBOTS_SITEMAPS
    ] + [
        ("sitemap.xml", f"{final_origin}/sitemap.xml"),
        ("sitemap_index.xml", f"{final_origin}/sitemap_index.xml"),
    ]
    signals.sitemap, listed = probe.sitemaps(
        candidates, scope_origins, include, required=False
    )

    samples, level_two = probe.sample(
        level_one, include, allowed, set(level_one) | itself, scope_origins
    )
    signals.sample_pages = samples
    linked = set(level_one) | level_two
    # A duplicate was fetched too; its links are those of the page it repeats.
    sampled = sum(1 for item in samples if item["outcome"] in ("included", "duplicate"))
    if not level_one:
        frontier = "closed"
    elif sampled:
        frontier = "closed" if not level_two else "open"
    else:
        frontier = "unknown"
    signals.links = {
        "l1": len(level_one),
        "l2": len(level_two),
        "linked_total": len(linked),
        "sampled": sampled,
        "sample_failed": len(samples) - sampled,
        "frontier": frontier,
    }
    signals.sitemap["linked_in_sitemap"] = len(linked & listed)
    signals.sections = _sections(include, linked, listed)
    return signals


def _probe_sitemap(probe: _Probe, selection: dict) -> ProbeSignals:
    """Sitemap input: robots of its origin, then the sitemap itself."""
    sitemap_url = canonical_url(selection["sitemap_url"])
    origin = url_origin(sitemap_url)
    signals = ProbeSignals(
        probe_mode="sitemap", entered_url=sitemap_url, entered_origin=origin
    )
    probe.step("robots", 10)
    signals.robots = probe.robots(origin, {origin}, None)
    signals.sitemap, listed = probe.sitemaps(
        [("input", sitemap_url)], {origin}, [], required=True
    )
    signals.sitemap["url"] = sitemap_url[:MAX_RECORDED_URL_CHARS]
    signals.sections = _sections([], set(), listed)
    return signals


def _probe_url_list(probe: _Probe, selection: dict) -> ProbeSignals:
    """URL list: robots of up to 5 origins and the first URL of up to 3."""
    urls = [canonical_url(str(url)) for url in selection["urls"]]
    origins = list(dict.fromkeys(url_origin(url) for url in urls))
    signals = ProbeSignals(
        probe_mode="url_list", entered_url=urls[0], entered_origin=origins[0]
    )
    probe.step("robots", 10)
    blocked = 0
    checked = []
    for origin in origins[:MAX_URL_LIST_ROBOTS]:
        try:
            facts = probe.robots(origin, {origin}, None)
        except ConnectorFailure as exc:
            if exc.issue.code in EXHAUSTED:
                break
            facts = {
                "origin": origin,
                "found": None,
                "status": None,
                "crawl_delay": None,
                "start_allowed": False,
                "sitemaps": [],
                "error": exc.issue.code,
            }
        else:
            blocked += sum(
                1
                for url in urls
                if url_origin(url) == origin and not probe.robots_allow(url)
            )
        facts.pop("sitemaps", None)
        checked.append(facts)
    if checked:
        signals.robots, signals.extra_robots = checked[0], checked[1:]
    if blocked:
        signals.warnings.append("robots_blocks_urls")

    probe.step("start_page", 40)
    probe.transport.purpose = "start_page"
    firsts = [
        next(url for url in urls if url_origin(url) == origin)
        for origin in origins[:MAX_URL_LIST_PAGES]
    ]
    firsts = [url for url in firsts if probe.robots_allow(url)]
    pages = []
    if firsts:
        store = probe.crawl(
            {"mode": "url_list", "urls": firsts},
            list(dict.fromkeys(url_origin(url) for url in firsts)),
            len(firsts),
        )
        artifacts = {item.canonical_location: item for item in store.artifacts}
        for outcome in store.outcomes:
            artifact = artifacts.get(outcome.canonical_location or "")
            page = {
                "url": _without_query(outcome.canonical_location or ""),
                "outcome": outcome.status,
                "media_type": outcome.media_type,
                "text_length": None,
            }
            if artifact is not None and artifact.media_type == "text/html":
                page["text_length"] = _page_links(
                    artifact.content, outcome.canonical_location
                )[1]
                if _client_rendered(artifact) and "client_rendered" not in (
                    signals.warnings
                ):
                    signals.warnings.append("client_rendered")
            pages.append(page)
        store.artifacts.clear()
    signals.url_list = {
        "count": len(urls),
        "origins": [origin[:MAX_RECORDED_URL_CHARS] for origin in origins[:20]],
        "origin_count": len(origins),
        "robots_checked": len(checked),
        "robots_blocked": blocked,
        "pages": pages[:MAX_URL_LIST_PAGES],
    }
    return signals
