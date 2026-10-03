"""Bounded, non-executing Website discovery for source previews and runs."""

from __future__ import annotations

import hashlib
import random
import threading
import time
import xml.etree.ElementTree as ET
import zlib
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import unquote, unquote_plus, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.safe_http import SafeHttpClient, canonical_url, failure, url_origin
from app.schemas.ingestion import WebsiteConfig, WebsiteFetchPolicy

# Effective deadlines allow this much slack over the time the configured
# request rate needs, so slow responses do not end a valid crawl early.
DEADLINE_SAFETY_FACTOR = 1.5
# A sitemap index is followed one level deep, to at most this many sitemaps.
MAX_NESTED_SITEMAPS = 50
# Links read from one page; admission limits still bound what is recorded.
MAX_PAGE_LINKS = 4000
# Discovered URLs longer than this (UTF-8 bytes) are excluded, and any frontier
# key is cut to it, staying well inside PostgreSQL's btree entry limit.
MAX_URL_BYTES = 2000
# HTTP statuses and transport failures worth another attempt.
RETRY_STATUSES = frozenset({429, 502, 503, 504})
RETRY_FAILURES = frozenset({"request_timeout", "request_failed", "truncated_response"})
SITEMAP_MEDIA = frozenset({"application/xml", "text/xml", "application/rss+xml"})
GZIP_MEDIA = frozenset({"application/gzip", "application/x-gzip"})


class WebsiteScopeTooLarge(ValueError):
    """The selected pages cannot be fetched at the selected speed in time."""


def _page_budget(config: WebsiteConfig) -> tuple[int, int]:
    selection = config.selection
    if selection.mode == "single_url":
        return 1, 0
    if selection.mode == "url_list":
        return len(selection.urls), 0
    if selection.mode == "sitemap":
        return config.max_pages, 0
    return config.max_pages, config.max_depth


def _overhead_requests(config: WebsiteConfig) -> int:
    """robots.txt per allowed origin plus the sitemap and its nested sitemaps."""
    return len(config.allowed_origins) + (
        1 + MAX_NESTED_SITEMAPS if config.selection.mode == "sitemap" else 0
    )


def resolve_website_fetch_policy(config: object, settings) -> WebsiteFetchPolicy:
    """Combine user scope with server-owned limits; the only place that does."""
    parsed = WebsiteConfig.model_validate(config)
    pages, depth = _page_budget(parsed)
    requests = pages + _overhead_requests(parsed)
    needed = requests / parsed.requests_per_second
    if needed > settings.website_deadline_max_seconds:
        raise WebsiteScopeTooLarge(
            f"{pages} pages at {parsed.requests_per_second:g} requests per second "
            f"need about {needed:.0f} seconds, beyond the server's "
            f"{settings.website_deadline_max_seconds:.0f}-second crawl limit. "
            "Lower maximum pages or raise crawl speed."
        )
    deadline = min(
        max(
            needed * DEADLINE_SAFETY_FACTOR + settings.website_request_timeout_seconds,
            settings.website_deadline_min_seconds,
        ),
        settings.website_deadline_max_seconds,
    )
    return WebsiteFetchPolicy(
        policy_version=3,
        max_pages=pages,
        max_depth=depth,
        requests_per_second=parsed.requests_per_second,
        request_timeout_seconds=settings.website_request_timeout_seconds,
        max_response_bytes=settings.website_max_response_bytes,
        max_total_bytes=min(
            pages * settings.website_max_response_bytes,
            settings.website_max_total_bytes_cap,
        ),
        redirect_limit=settings.website_redirect_limit,
        user_agent=settings.website_user_agent,
        deadline_seconds=round(deadline, 3),
        retry_attempts=settings.website_retry_attempts,
        retry_base_delay_seconds=settings.website_retry_base_delay_seconds,
        retry_max_delay_seconds=settings.website_retry_max_delay_seconds,
        fetch_concurrency=settings.website_fetch_concurrency,
    )


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
    provider_revision: str | None = None
    # Requests made for this item, including transient retries; 0 if none.
    attempts: int = 0


@dataclass(frozen=True)
class PriorWebsiteRevision:
    """A stored page; its body is loaded only when a refresh reuses it."""

    content: bytes | None = None
    media_type: str = "text/html"
    etag: str | None = None
    last_modified: str | None = None
    fetched_at: datetime | None = None
    loader: Callable[[], bytes] | None = None

    def body(self) -> bytes:
        return self.content if self.content is not None else self.loader()


@dataclass(frozen=True)
class WebsiteArtifact:
    canonical_location: str
    content: bytes
    media_type: str
    etag: str | None
    last_modified: str | None
    validator_unchanged: bool
    depth: int


@dataclass(frozen=True)
class CrawlEntry:
    """A queued URL; `key` lets a persistent store find its row again."""

    url: str
    depth: int
    lastmod: datetime | None = None
    key: object = None
    # The discovered URL before tracking parameters were removed, if any were.
    original: str | None = None


@dataclass(frozen=True)
class CrawlAdmission:
    """One discovery decision: a queued entry, a final outcome or a repeat URL."""

    entry: CrawlEntry | None = None
    outcome: PreviewOutcome | None = None
    key: str | None = None
    duplicate_of: str | None = None
    original: str | None = None
    # Fetch before other queued URLs: a canonical target stands in for a page
    # already marked duplicate, so the page limit must not exclude it.
    priority: bool = False


@dataclass(frozen=True)
class PageResult:
    outcome: PreviewOutcome
    artifact: WebsiteArtifact | None = None
    links: list[str] = field(default_factory=list)
    # An in-scope rel="canonical" target to discover instead of this page.
    canonical: str | None = None
    # Hash of the page's normalized visible text, for duplicate content.
    content_hash: str | None = None


@dataclass(frozen=True)
class CrawlResume:
    seeded: bool = False
    transferred: int = 0
    elapsed_seconds: float = 0.0
    fetched_pages: int = 0


@dataclass(frozen=True)
class CrawlProgress:
    transferred: int
    elapsed_seconds: float


def duplicate_outcome(url: str, original: str | None = None) -> PreviewOutcome:
    note = (
        f" Tracking parameters were removed from {original}."
        if original and original != url
        else ""
    )
    return PreviewOutcome(
        external_id=original or url,
        display_name=url,
        canonical_location=url,
        media_type=None,
        status="duplicate",
        reason=f"Duplicate canonical URL; fetched only once.{note}"[:500],
    )


# Query parameters that only track a visit; removed before URLs are compared.
TRACKING_PARAMETERS = frozenset({"ref", "fbclid", "gclid"})
# Pages with less normalized text than this are not compared by content, so
# near-empty pages (such as JavaScript shells) are not merged with each other.
MIN_DEDUPLICATED_TEXT_CHARS = 200


def _is_tracking(segment: str) -> bool:
    key = unquote_plus(segment.split("=", 1)[0]).lower()
    return key.startswith("utm_") or key in TRACKING_PARAMETERS


def strip_tracking(url: str) -> str:
    """Remove utm_* and other documented tracking parameters from a canonical URL.

    Other parameters keep their order and exact encoding, so a URL without
    tracking parameters is returned unchanged.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    segments = parts.query.split("&")
    kept = [segment for segment in segments if not _is_tracking(segment)]
    if len(kept) == len(segments):
        return url
    return urlunsplit(parts._replace(query="&".join(kept)))


def bounded_key(value: str) -> str:
    """`value`, or a prefix plus a digest when it exceeds MAX_URL_BYTES."""
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_URL_BYTES:
        return value
    prefix = encoded[: MAX_URL_BYTES - 80].decode("utf-8", errors="ignore")
    return f"{prefix}…#sha256={hashlib.sha256(encoded).hexdigest()}"


def record_state(states: dict[str, str], url: str, result: PageResult) -> None:
    """Remember a completed page under its queued URL and its final URL."""
    status = "fetched" if result.outcome.status == "included" else result.outcome.status
    states[url] = status
    if result.outcome.canonical_location:
        states.setdefault(result.outcome.canonical_location, status)


class MemoryCrawlStore:
    """Crawl state held in memory, for previews; runs use a persistent store."""

    def __init__(self):
        self.outcomes: list[PreviewOutcome] = []
        self.artifacts: list[WebsiteArtifact] = []
        self._known: set[str] = set()
        self._pages = 0
        self._duplicates: set[str] = set()
        self._queue: deque[CrawlEntry] = deque()
        self._omitted = False
        self._content: dict[str, str] = {}
        self._states: dict[str, str] = {}

    def resume(self) -> CrawlResume:
        return CrawlResume()

    def url_state(self, url: str) -> str | None:
        """queued, fetched (included), another final status, or None if unknown."""
        return self._states.get(url)

    def count(self) -> int:
        return self._pages

    def omitted(self) -> bool:
        return self._omitted

    def mark_omitted(self) -> None:
        self._omitted = True

    def is_known(self, url: str) -> bool:
        return url in self._known

    def reserve(self, url: str, *, sitemap: bool = False) -> None:
        self._known.add(url)
        self._pages += not sitemap

    def mark_duplicate(self, url: str) -> bool:
        if url in self._duplicates:
            return False
        self._duplicates.add(url)
        return True

    def commit(
        self, completion, admissions, progress, *, seeded=False, reinstate=False
    ) -> bool:
        if completion is not None:
            entry, result = completion
            if reinstate:
                # Replace the duplicate outcome recorded for this page earlier.
                position = next(
                    index
                    for index, item in reversed(list(enumerate(self.outcomes)))
                    if item.canonical_location == result.outcome.canonical_location
                    and item.status == "duplicate"
                )
                self.outcomes[position] = result.outcome
            else:
                self.outcomes.append(result.outcome)
            record_state(self._states, entry.url, result)
            if result.artifact is not None:
                self.artifacts.append(result.artifact)
                if result.content_hash:
                    self._content[result.content_hash] = (
                        result.outcome.canonical_location
                    )
        for admission in admissions:
            if admission.entry is not None:
                if admission.priority:
                    self._queue.appendleft(admission.entry)
                else:
                    self._queue.append(admission.entry)
                self._states[admission.entry.url] = "queued"
            elif admission.duplicate_of is not None:
                self.outcomes.append(
                    duplicate_outcome(admission.duplicate_of, admission.original)
                )
            else:
                self.outcomes.append(admission.outcome)
                if admission.key:
                    self._states[admission.key] = admission.outcome.status
        return True

    def next_queued(self) -> CrawlEntry | None:
        return self._queue.popleft() if self._queue else None

    def has_queued(self) -> bool:
        return bool(self._queue)

    def drain_queued(self) -> list[CrawlEntry]:
        entries = list(self._queue)
        self._queue.clear()
        return entries

    def prioritize(self, url: str) -> None:
        _move_to_front(self._queue, url)

    def content_owner(self, content_hash: str) -> str | None:
        return self._content.get(content_hash)


def _move_to_front(queue: deque, url: str) -> None:
    for position, entry in enumerate(queue):
        if entry.url == url:
            del queue[position]
            queue.appendleft(entry)
            return


def _total_exceeded():
    return failure(
        "total_bytes_exceeded", "The website crawl exceeded its total byte limit."
    )


class _ByteBudget:
    """Total-byte accounting shared by fetch threads.

    Bytes are counted atomically when a response arrives, so the accepted total
    never exceeds the limit. Nothing is reserved while a request is in flight:
    reserving the per-page maximum for every parallel request refused pages long
    before the budget was used.
    """

    def __init__(self, limit: int, used: int):
        self._lock = threading.Lock()
        self._limit = limit
        self._used = used

    def remaining(self) -> int:
        with self._lock:
            return self._limit - self._used

    def consume(self, transferred: int) -> None:
        with self._lock:
            if self._used + transferred > self._limit:
                raise _total_exceeded()
            self._used += transferred

    def used(self) -> int:
        with self._lock:
            return self._used


class _OriginRateLimiter:
    """Spaces request starts per origin, shared by every fetch thread."""

    def __init__(self, clock, sleeper):
        self._lock = threading.Lock()
        self._clock = clock
        self._sleeper = sleeper
        self._last: dict[str, float] = {}

    def wait(
        self, origin: str, interval: float, deadline: float | None = None
    ) -> float:
        """Sleep until this origin's next request slot.

        A slot at or after `deadline` is not taken: the request fails at once
        instead of sleeping past the crawl's time limit.
        """
        with self._lock:
            now = self._clock()
            previous = self._last.get(origin)
            slot = now if previous is None else max(now, previous + interval)
            if deadline is not None and slot >= deadline:
                raise failure(
                    "deadline_exceeded",
                    "The website crawl exceeded its deadline.",
                )
            self._last[origin] = slot
        delay = slot - self._clock()
        if delay > 0:
            self._sleeper(delay)
        return slot


class _Links(HTMLParser):
    """Links, the first rel=canonical target and normalized visible text."""

    SKIPPED = frozenset({"script", "style", "noscript", "template"})

    def __init__(self, limit: int):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.links: list[str] = []
        self.canonical: str | None = None
        self._text: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIPPED:
            self._skipping += 1
            return
        values = {key.lower(): value for key, value in attrs if value}
        if (
            tag == "link"
            and self.canonical is None
            and "canonical" in (values.get("rel") or "").lower().split()
            and values.get("href")
        ):
            self.canonical = values["href"]
        elif (
            tag in ("a", "area") and len(self.links) < self.limit and values.get("href")
        ):
            self.links.append(values["href"])

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIPPED and self._skipping:
            self._skipping -= 1

    def handle_data(self, data):
        if not self._skipping:
            self._text.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._text).split())


def _media_type(headers: dict[str, str]) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _local_name(element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _child_text(element, name: str) -> str:
    for child in element:
        if _local_name(child) == name:
            return (child.text or "").strip()
    return ""


def _parse_lastmod(value: str) -> datetime | None:
    """The latest moment a sitemap <lastmod> can mean.

    A date alone ("2026-10-02") may be any time that day, so it means the end
    of the day: a page stored earlier that day is still refetched.
    """
    if not value or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if len(value) == 10:  # YYYY-MM-DD
        parsed += timedelta(days=1)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _retry_after_seconds(headers: dict[str, str], now: datetime) -> float | None:
    value = (headers.get("retry-after") or "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (moment - now).total_seconds())


def _gunzip(content: bytes, limit: int) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        output = decompressor.decompress(content, limit + 1)
    except zlib.error as exc:
        raise failure(
            "invalid_sitemap", "The compressed sitemap is malformed."
        ) from exc
    if len(output) > limit or decompressor.unconsumed_tail:
        raise failure(
            "sitemap_too_large",
            "The decompressed sitemap exceeds the per-page byte limit.",
        )
    if not decompressor.eof:
        raise failure("invalid_sitemap", "The compressed sitemap is truncated.")
    return output


class WebsiteConnector:
    kind = "website"
    config_version = "1"

    def __init__(
        self,
        *,
        client: SafeHttpClient | None = None,
        clock=time.monotonic,
        sleeper=time.sleep,
        jitter=random.random,
        wall_clock=lambda: datetime.now(timezone.utc),
    ):
        self.client = client or SafeHttpClient()
        self.clock = clock
        self.sleeper = sleeper
        self.jitter = jitter
        self.wall_clock = wall_clock

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
        # Path filters narrow what crawling and sitemaps discover; URLs the user
        # entered directly are fetched whatever filters are saved.
        filtered = config.selection.mode in ("crawl", "sitemap")

        def origin_allowed(url: str):
            return url_origin(url) in origins

        def page_allowed(url: str):
            if not origin_allowed(url):
                return False
            if not filtered:
                return True
            path = unquote(urlsplit(url).path or "/")
            if config.include_path_prefixes and not any(
                path.startswith(prefix) for prefix in config.include_path_prefixes
            ):
                return False
            return not any(
                path.startswith(prefix) for prefix in config.exclude_path_prefixes
            )

        return origin_allowed, page_allowed

    def crawl(
        self,
        config: object,
        policy: WebsiteFetchPolicy,
        priors: dict[str, PriorWebsiteRevision] | None,
        store,
    ) -> bool:
        """Crawl into `store`, resuming from what it already holds.

        Fetches run on up to `policy.fetch_concurrency` threads; every decision
        and every store write happens on the calling thread, so a fenced store can
        reject a stale worker. Returns False if the store stopped the crawl.
        """
        # Scope comes from the node; every limit comes from the recorded policy.
        parsed = WebsiteConfig.model_validate(config)
        policy = WebsiteFetchPolicy.model_validate(policy)
        priors = priors or {}
        origin_allowed, page_allowed = self._scope(parsed)
        resume = store.resume()
        started = self.clock()
        deadline = started + max(0.0, policy.deadline_seconds - resume.elapsed_seconds)
        budget = _ByteBudget(policy.max_total_bytes, resume.transferred)
        limiter = _OriginRateLimiter(self.clock, self.sleeper)
        robots: dict[str, RobotFileParser | ConnectorIssue | None] = {}
        # One lock per origin, so a slow robots.txt only delays its own origin.
        robots_locks: dict[str, threading.Lock] = {}
        robots_guard = threading.Lock()
        stopping = threading.Event()
        crawl = parsed.selection.mode == "crawl"

        def interval_for(url: str) -> float:
            interval = 1 / policy.requests_per_second
            rules = robots.get(url_origin(url))
            if isinstance(rules, RobotFileParser):
                crawl_delay = rules.crawl_delay(policy.user_agent)
                if crawl_delay:
                    # robots.txt may only slow the crawl down, never speed it up.
                    interval = max(interval, float(crawl_delay))
            return interval

        def retry_delay(attempt: int, retry_after: float | None) -> float | None:
            """Seconds to wait before another attempt, or None to stop."""
            if attempt >= policy.retry_attempts:
                return None
            # Retry-After is honored up to the policy's maximum delay.
            backoff = policy.retry_base_delay_seconds * 2 ** (attempt - 1)
            delay = min(
                max(backoff * (1 + self.jitter()), retry_after or 0),
                policy.retry_max_delay_seconds,
            )
            if self.clock() + delay + 1 >= deadline:
                return None
            return delay

        def request(
            url: str,
            tally: list[int],
            *,
            page_scope=True,
            validators=None,
            gzip=False,
            any_5xx=False,
        ):
            """One logical request with transient retries; `tally[0]` counts tries."""

            def before_redirect(next_url: str):
                # Every redirect hop is a request to a site: it keeps the
                # origin's rate and, for pages, that origin's robots.txt rules.
                if stopping.is_set():
                    raise failure("crawl_stopped", "The crawl was stopped.")
                if page_scope and not robots_allowed(next_url, [0]):
                    raise failure(
                        "robots_disallowed",
                        f"robots.txt disallows the redirect target {next_url[:300]}.",
                    )
                limiter.wait(url_origin(next_url), interval_for(next_url), deadline)

            while True:
                if stopping.is_set():
                    raise failure("crawl_stopped", "The crawl was stopped.")
                remaining = budget.remaining()
                if remaining <= 0:
                    raise _total_exceeded()
                limiter.wait(url_origin(url), interval_for(url), deadline)
                tally[0] += 1
                try:
                    response = self.client.get(
                        url,
                        user_agent=policy.user_agent,
                        request_timeout=policy.request_timeout_seconds,
                        deadline=deadline,
                        redirect_limit=policy.redirect_limit,
                        max_response_bytes=policy.max_response_bytes,
                        max_total_bytes=remaining,
                        allowed=page_allowed if page_scope else origin_allowed,
                        request_headers=validators,
                        allow_gzip_encoding=gzip,
                        before_redirect=before_redirect,
                    )
                except ConnectorFailure as exc:
                    if (
                        exc.issue.code == "response_too_large"
                        and remaining < policy.max_response_bytes
                    ):
                        # Only the rest of the crawl's budget was left for it.
                        raise _total_exceeded() from exc
                    delay = (
                        retry_delay(tally[0], None)
                        if exc.issue.code in RETRY_FAILURES
                        else None
                    )
                    if delay is None:
                        raise
                    self.sleeper(delay)
                    continue
                budget.consume(response.transferred_bytes)
                transient = response.status in RETRY_STATUSES or (
                    any_5xx and 500 <= response.status < 600
                )
                if not transient:
                    return response
                delay = retry_delay(
                    tally[0], _retry_after_seconds(response.headers, self.wall_clock())
                )
                if delay is None:
                    return response
                self.sleeper(delay)

        def robots_allowed(url: str, tally: list[int]):
            origin = url_origin(url)
            with robots_guard:
                lock = robots_locks.setdefault(origin, threading.Lock())
            # One robots.txt request per origin, even with parallel fetchers.
            with lock:
                if origin not in robots:
                    try:
                        response = request(
                            origin + "/robots.txt",
                            tally,
                            page_scope=False,
                            any_5xx=True,
                        )
                    except ConnectorFailure as exc:
                        robots[origin] = exc.issue
                        raise
                    if response.status == 404:
                        robots[origin] = None
                    elif 200 <= response.status < 300:
                        parser = RobotFileParser()
                        parser.set_url(response.url)
                        parser.parse(
                            response.content.decode(
                                "utf-8", errors="replace"
                            ).splitlines()
                        )
                        robots[origin] = parser
                    else:
                        # Retried already; record once so the origin's other pages
                        # fail without more requests. Not retryable by the worker.
                        robots[origin] = ConnectorIssue(
                            code="robots_unavailable",
                            message="robots.txt could not be checked safely.",
                            retryable=False,
                        )
            rules = robots[origin]
            if isinstance(rules, ConnectorIssue):
                raise ConnectorFailure(rules)
            return rules is None or rules.can_fetch(policy.user_agent, url)

        def outcome(url, status, reason, *, depth=None, **values):
            return PreviewOutcome(
                external_id=url,
                display_name=url,
                canonical_location=url,
                status=status,
                reason=reason,
                depth=depth,
                media_type=values.pop("media", None),
                size_bytes=values.pop("size", None),
                error_code=values.pop("code", None),
                **values,
            )

        # Out-of-scope links are listed until `discovery_limit` URLs are recorded;
        # in-scope URLs may use the same number again, so navigation links to other
        # sites or sections cannot use up the room for the pages being crawled.
        discovery_limit = min(4000, policy.max_pages * 4)
        record_limit = discovery_limit * 2

        def excluded_once(key: str, reason: str, depth, code=None):
            """Record an unusable URL once; repeats of it are ignored."""
            key = bounded_key(key)
            if store.is_known(key) or store.count() >= discovery_limit:
                return None
            store.reserve(key)
            return CrawlAdmission(
                outcome=outcome(key, "excluded", reason, depth=depth, code=code),
                key=key,
            )

        def admit(
            raw_url: str, depth: int, lastmod=None, *, force: bool = False
        ) -> CrawlAdmission | None:
            """Decide scope for one discovered URL before it is queued.

            `force` admits a rel=canonical target past the discovery limits: the
            page that declared it is indexed only through it.
            """
            if not force and store.count() >= record_limit:
                if not store.omitted():
                    store.mark_omitted()
                    return CrawlAdmission(
                        outcome=outcome(
                            None,
                            "excluded",
                            "Additional URLs were omitted by the discovery limit.",
                        )
                    )
                return None
            scheme = urlsplit(raw_url).scheme.lower()
            if scheme == "":
                # Page links arrive absolute; this is a relative sitemap <loc>.
                return excluded_once(
                    raw_url, "The URL is not absolute. The link was skipped.", depth
                )
            if scheme not in ("http", "https"):
                # mailto:, tel:, javascript: and similar links are not pages.
                return None
            try:
                discovered = canonical_url(raw_url)
            except ConnectorFailure as exc:
                return excluded_once(
                    raw_url,
                    f"{exc.issue.message} The link was skipped.",
                    depth,
                    exc.issue.code,
                )
            url = strip_tracking(discovered)
            original = discovered if discovered != url else None
            if len(url.encode("utf-8")) > MAX_URL_BYTES:
                return excluded_once(
                    url,
                    f"URL is longer than {MAX_URL_BYTES:,} bytes and was skipped.",
                    depth,
                )
            if store.is_known(url):
                if store.mark_duplicate(url):
                    return CrawlAdmission(duplicate_of=url, original=original)
                return None
            reason = None
            if not origin_allowed(url):
                reason = "URL origin is outside the configured allowlist."
            elif not page_allowed(url):
                reason = "URL path is outside the configured include/exclude rules."
            elif depth > policy.max_depth:
                reason = "URL exceeds the configured crawl depth."
            if reason and not force and store.count() >= discovery_limit:
                return None
            store.reserve(url)
            if reason:
                return CrawlAdmission(
                    outcome=outcome(url, "excluded", reason, depth=depth), key=url
                )
            return CrawlAdmission(
                entry=CrawlEntry(url, depth, lastmod, original=original)
            )

        def fetch_sitemap(url: str, tally: list[int]):
            """The parsed XML root of a sitemap; gzip is decompressed within limits."""
            response = request(url, tally, page_scope=False, gzip=True)
            if not 200 <= response.status < 300:
                raise failure(
                    "sitemap_request_failed",
                    f"The sitemap could not be fetched (HTTP {response.status}).",
                )
            media = _media_type(response.headers)
            content = response.content
            compressed = (
                urlsplit(response.url).path.lower().endswith(".gz")
                or media in GZIP_MEDIA
                or response.headers.get("content-encoding", "").lower() == "gzip"
            )
            if compressed:
                content = _gunzip(content, policy.max_response_bytes)
            elif media not in SITEMAP_MEDIA:
                raise failure(
                    "unsupported_sitemap", "The sitemap response must be XML."
                )
            upper = content.upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise failure(
                    "unsafe_sitemap",
                    "Sitemaps with document types or entities are not accepted.",
                )
            try:
                return ET.fromstring(content)
            except ET.ParseError as exc:
                raise failure(
                    "invalid_sitemap", "The sitemap XML is malformed."
                ) from exc

        def sitemap_pages(root, room: int):
            """Up to `room` listed pages; admission could never record more."""
            pages = []
            for element in root.iter():
                if len(pages) >= room:
                    break
                if _local_name(element) == "url" and (
                    loc := _child_text(element, "loc")
                ):
                    pages.append(
                        (loc, 0, _parse_lastmod(_child_text(element, "lastmod")))
                    )
            return pages

        def seed() -> list[CrawlAdmission]:
            selection = parsed.selection
            if selection.mode == "single_url":
                pages = [(str(selection.url), 0, None)]
            elif selection.mode == "url_list":
                pages = [(str(url), 0, None) for url in selection.urls]
            elif crawl:
                pages = [(str(selection.start_url), 0, None)]
            else:
                pages = []
            admissions: list[CrawlAdmission] = []
            if selection.mode == "sitemap":
                try:
                    root = fetch_sitemap(str(selection.sitemap_url), [0])
                except ConnectorFailure as exc:
                    # Transient failures were already retried here; a worker retry
                    # of the whole source would repeat them.
                    raise ConnectorFailure(
                        exc.issue.model_copy(update={"retryable": False})
                    ) from exc
                if _local_name(root) != "sitemapindex":
                    pages = sitemap_pages(root, record_limit)
                else:
                    nested = [
                        loc
                        for element in root.iter()
                        if _local_name(element) == "sitemap"
                        and (loc := _child_text(element, "loc"))
                    ]
                    for raw_url in nested[:MAX_NESTED_SITEMAPS]:
                        tally = [0]
                        try:
                            url = canonical_url(raw_url)
                            if len(url.encode("utf-8")) > MAX_URL_BYTES:
                                raise failure(
                                    "invalid_url", "The sitemap URL is too long."
                                )
                        except ConnectorFailure as exc:
                            admission = excluded_once(
                                raw_url,
                                f"Nested sitemap skipped: {exc.issue.message}",
                                None,
                                exc.issue.code,
                            )
                            if admission is not None:
                                admissions.append(admission)
                            continue
                        if store.is_known(url):
                            # Listed twice in the index; one row per URL.
                            continue
                        if not origin_allowed(url):
                            item = outcome(
                                url,
                                "excluded",
                                "Nested sitemap origin is outside the configured "
                                "allowlist.",
                            )
                        else:
                            try:
                                child = fetch_sitemap(url, tally)
                            except ConnectorFailure as exc:
                                item = outcome(
                                    url,
                                    "failed",
                                    exc.issue.message,
                                    code=exc.issue.code,
                                    attempts=tally[0],
                                )
                            else:
                                if _local_name(child) == "sitemapindex":
                                    item = outcome(
                                        url,
                                        "excluded",
                                        "Nested sitemap indexes are followed only one "
                                        "level deep.",
                                        attempts=tally[0],
                                    )
                                else:
                                    listed = sitemap_pages(
                                        child, max(0, record_limit - len(pages))
                                    )
                                    pages.extend(listed)
                                    item = outcome(
                                        url,
                                        "sitemap",
                                        f"Nested sitemap; listed {len(listed)} page "
                                        "URLs for discovery.",
                                        media="application/xml",
                                        attempts=tally[0],
                                    )
                        store.reserve(url, sitemap=item.status == "sitemap")
                        admissions.append(CrawlAdmission(outcome=item, key=url))
                    if len(nested) > MAX_NESTED_SITEMAPS:
                        admissions.append(
                            CrawlAdmission(
                                outcome=outcome(
                                    None,
                                    "excluded",
                                    f"{len(nested) - MAX_NESTED_SITEMAPS} more nested "
                                    f"sitemaps were omitted by the "
                                    f"{MAX_NESTED_SITEMAPS}-sitemap limit.",
                                )
                            )
                        )
            for raw_url, depth, lastmod in pages:
                admission = admit(raw_url, depth, lastmod)
                if admission is not None:
                    admissions.append(admission)
            return admissions

        def canonical_target(href: str, page_url: str, requested: str):
            """(target, None) to follow rel=canonical, or (None, note) to ignore it.

            A canonical naming the page itself, including the URL requested
            before a redirect (`/a` redirecting to `/a/` that declares `/a`), is
            not a duplicate.
            """
            try:
                target = strip_tracking(canonical_url(href, base=page_url))
            except ConnectorFailure:
                return None, "Ignored an invalid rel=canonical URL."
            if target in (strip_tracking(page_url), requested):
                return None, None
            if len(target.encode("utf-8")) > MAX_URL_BYTES:
                return None, "Ignored a rel=canonical URL that is too long."
            if not page_allowed(target):
                return None, (
                    f"Ignored rel=canonical {target[:300]}: outside the configured "
                    "origins or paths."
                )
            return target, None

        def fetch_page(entry: CrawlEntry) -> PageResult:
            """Runs on a fetch thread; returns the decided outcome, never writes."""
            url, depth, tally = entry.url, entry.depth, [0]
            try:
                if not robots_allowed(url, tally):
                    return PageResult(
                        outcome(
                            url,
                            "excluded",
                            "robots.txt disallows this URL.",
                            depth=depth,
                            attempts=tally[0],
                        )
                    )
                tally[0] = 0
                prior = priors.get(url)
                if (
                    prior is not None
                    and entry.lastmod is not None
                    and prior.fetched_at is not None
                    and entry.lastmod <= prior.fetched_at
                    and prior.media_type == "text/html"
                ):
                    # The sitemap says the page has not changed since it was stored.
                    content = prior.body()
                    return PageResult(
                        outcome(
                            url,
                            "included",
                            "Unchanged since the stored copy by sitemap lastmod; "
                            "reused without a request.",
                            media=prior.media_type,
                            size=len(content),
                            depth=depth,
                        ),
                        WebsiteArtifact(
                            canonical_location=url,
                            content=content,
                            media_type=prior.media_type,
                            etag=prior.etag,
                            last_modified=prior.last_modified,
                            validator_unchanged=True,
                            depth=depth,
                        ),
                    )
                validators = {}
                if prior and prior.etag:
                    validators["If-None-Match"] = prior.etag
                if prior and prior.last_modified:
                    validators["If-Modified-Since"] = prior.last_modified
                response = request(url, tally, validators=validators)
                validator_unchanged = response.status == 304
                if validator_unchanged and prior is None:
                    raise failure(
                        "invalid_not_modified",
                        "Website returned not-modified without a prior revision.",
                    )
                if response.status != 304 and not 200 <= response.status < 300:
                    return PageResult(
                        outcome(
                            url,
                            "failed",
                            f"Website returned HTTP {response.status}"
                            + (f" after {tally[0]} attempts." if tally[0] > 1 else "."),
                            depth=depth,
                            code="http_status",
                            attempts=tally[0],
                        )
                    )
                content = prior.body() if validator_unchanged else response.content
                media = (
                    prior.media_type
                    if validator_unchanged
                    else _media_type(response.headers)
                )
                if media != "text/html":
                    return PageResult(
                        outcome(
                            response.url,
                            "excluded",
                            "Only HTML pages are supported in Website preview.",
                            media=media or None,
                            size=len(content),
                            depth=depth,
                            attempts=tally[0],
                        )
                    )
                # Navigation often precedes content links, so read enough of the page.
                parser = _Links(MAX_PAGE_LINKS)
                parser.feed(content.decode("utf-8", errors="replace"))
                notes = []
                if entry.original:
                    notes.append(
                        f"Tracking parameters were removed from {entry.original}."
                    )
                target = None
                if parser.canonical:
                    # Whether the target replaces this page is decided on the
                    # coordinating thread, which knows what the crawl indexed.
                    target, note = canonical_target(parser.canonical, response.url, url)
                    if note:
                        notes.append(note)
                text = parser.text()
                links = (
                    [urljoin(response.url, link) for link in parser.links]
                    if crawl and depth < policy.max_depth
                    else []
                )
                return PageResult(
                    outcome(
                        response.url,
                        "included",
                        " ".join(["HTML page is within scope and fetchable.", *notes])[
                            :500
                        ],
                        media=media,
                        size=len(content),
                        depth=depth,
                        attempts=tally[0],
                    ),
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
                    ),
                    links,
                    canonical=target,
                    content_hash=(
                        hashlib.sha256(text.encode("utf-8")).hexdigest()
                        if len(text) >= MIN_DEDUPLICATED_TEXT_CHARS
                        else None
                    ),
                )
            except ConnectorFailure as exc:
                if exc.issue.code == "robots_disallowed":
                    return PageResult(
                        outcome(
                            url,
                            "excluded",
                            exc.issue.message,
                            depth=depth,
                            attempts=tally[0],
                        )
                    )
                message = exc.issue.message
                if exc.issue.code == "response_too_large":
                    # Failing keeps the index complete; say how to proceed.
                    message = (
                        "The page is larger than the "
                        f"{policy.max_response_bytes / (1024 * 1024):g} MiB per-page "
                        "limit. Exclude its path under Filter pages, or ask an "
                        "administrator to raise WEBSITE_MAX_RESPONSE_BYTES."
                    )
                return PageResult(
                    outcome(
                        url,
                        "failed",
                        message,
                        depth=depth,
                        code=exc.issue.code,
                        attempts=tally[0],
                    )
                )

        def progress() -> CrawlProgress:
            return CrawlProgress(
                transferred=budget.used(),
                elapsed_seconds=resume.elapsed_seconds + (self.clock() - started),
            )

        if not resume.seeded:
            if not store.commit(None, seed(), progress(), seeded=True):
                return False

        def resolve_canonical(entry: CrawlEntry, result: PageResult):
            """Apply a page's rel=canonical; returns (result, admissions).

            The page becomes a duplicate only while its target is queued or
            indexed. A target that was excluded, failed or is itself a duplicate
            (two pages naming each other) cannot stand in for it, so the page is
            indexed and the reason says why.
            """
            target = result.canonical
            admissions = []
            state = store.url_state(target)
            if state is None:
                admission = admit(target, entry.depth, force=True)
                if admission is not None:
                    if admission.entry is not None:
                        admission = replace(admission, priority=True)
                    admissions.append(admission)
                    state = (
                        "queued"
                        if admission.entry is not None
                        else admission.outcome.status
                        if admission.outcome is not None
                        else store.url_state(target)
                    )
            if state in ("queued", "fetched"):
                if state == "queued":
                    # Fetch the target next, and keep this page's result until
                    # the target is indexed, in case it never is.
                    store.prioritize(target)
                    waiting.setdefault(target, []).append((entry, result))
                outcome_ = replace(
                    result.outcome,
                    status="duplicate",
                    reason=(
                        f"Declares {target} as its canonical URL; that page is "
                        "indexed instead."
                    )[:500],
                )
                # The target's own links are followed when it is fetched.
                return PageResult(outcome_), admissions
            return without_canonical(result), admissions

        def without_canonical(result: PageResult) -> PageResult:
            note = (
                f"Ignored rel=canonical {result.canonical[:300]}: that page is "
                "not indexed."
            )
            outcome_ = replace(
                result.outcome, reason=f"{result.outcome.reason} {note}"[:500]
            )
            return replace(result, outcome=outcome_, canonical=None)

        # Pages marked duplicate of a canonical target still being fetched.
        waiting: dict[str, list[tuple[CrawlEntry, PageResult]]] = {}

        def settle(entry: CrawlEntry, result: PageResult) -> bool:
            """Once a target is done, index the pages that deferred to it if
            it was not indexed itself (failed, excluded, or past the limits)."""
            covered = result.outcome.status in ("included", "duplicate")
            keys = {entry.url, result.outcome.canonical_location}
            for key in keys:
                for held_entry, held in waiting.pop(key, []):
                    if covered:
                        continue
                    if not record(held_entry, without_canonical(held), reinstate=True):
                        return False
            return True

        def record(entry: CrawlEntry, result: PageResult, *, reinstate=False) -> bool:
            nonlocal fetched
            admissions = []
            if result.canonical:
                result, admissions = resolve_canonical(entry, result)
            owner = (
                store.content_owner(result.content_hash)
                if result.content_hash and result.outcome.status == "included"
                else None
            )
            if owner is not None:
                result = PageResult(
                    replace(
                        result.outcome,
                        status="duplicate",
                        reason=f"Same content as {owner}; indexed once.",
                    )
                )
            if result.outcome.status == "included":
                fetched += 1
            admissions += [
                admission
                for link in result.links
                if (admission := admit(link, entry.depth + 1)) is not None
            ]
            if not store.commit(
                (entry, result), admissions, progress(), reinstate=reinstate
            ):
                return False
            return settle(entry, result)

        def drain(reason: str, status: str, code: str | None = None) -> bool:
            for entry in store.drain_queued():
                result = PageResult(
                    outcome(entry.url, status, reason, depth=entry.depth, code=code)
                )
                if not store.commit((entry, result), [], progress()):
                    return False
                if not settle(entry, result):
                    return False
            return True

        fetched = resume.fetched_pages
        # Results are decided in the order pages were queued, so which of two
        # identical pages is kept does not depend on which response came first.
        inflight: deque = deque()
        with ThreadPoolExecutor(max_workers=policy.fetch_concurrency) as pool:
            try:
                while True:
                    while (
                        len(inflight) < policy.fetch_concurrency
                        and fetched + len(inflight) < policy.max_pages
                        and self.clock() < deadline
                    ):
                        entry = store.next_queued()
                        if entry is None:
                            break
                        inflight.append((pool.submit(fetch_page, entry), entry))
                    if not inflight:
                        if store.has_queued():
                            if self.clock() >= deadline:
                                return drain(
                                    "The crawl deadline passed before this page "
                                    "was fetched.",
                                    "failed",
                                    "deadline_exceeded",
                                )
                            # Every remaining URL is beyond the page limit.
                            return drain(
                                "URL exceeds the configured page limit.", "excluded"
                            )
                        return True
                    future, entry = inflight.popleft()
                    if not record(entry, future.result()):
                        return False
            finally:
                # Stop requests in flight from retrying; their results are discarded.
                stopping.set()

    def _discover(
        self,
        config: object,
        policy: WebsiteFetchPolicy,
        priors: dict[str, PriorWebsiteRevision] | None = None,
    ) -> tuple[list[PreviewOutcome], list[WebsiteArtifact]]:
        store = MemoryCrawlStore()
        self.crawl(config, policy, priors, store)
        return store.outcomes, store.artifacts

    def discover_all(
        self, config: object, policy: WebsiteFetchPolicy
    ) -> list[PreviewOutcome]:
        return self._discover(config, policy)[0]

    def fetch_all(
        self,
        config: object,
        policy: WebsiteFetchPolicy,
        priors: dict[str, PriorWebsiteRevision] | None = None,
    ) -> tuple[list[PreviewOutcome], list[WebsiteArtifact]]:
        return self._discover(config, policy, priors)

    def discover(self, config: object, cursor: str | None = None):
        raise failure(
            "async_only", "Website discovery runs through an asynchronous preview job."
        )

    def fetch(self, item, prior_revision=None):
        raise failure(
            "preview_only", "Website ingestion is introduced in the next phase."
        )
